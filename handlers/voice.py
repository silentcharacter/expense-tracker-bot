"""Voice message handler: OGG → Gemini → Expense confirmation."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from models.expense import ExpenseSource
from handlers.expense_saving import save_expense
from services.tracing import RequestTracer

logger = logging.getLogger(__name__)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process an incoming voice message.

    Flow:
      1. Retrieve the registered user; prompt /start if absent.
      2. Download the OGG audio from Telegram.
      3. Send bytes to Gemini for transcription and expense parsing.
      4. Fetch the FX rate and compute amount_base.
      5. Build a pending ExpenseRecord and store it in user_data.
      6. Show a confirmation message with inline Save / Edit / Cancel buttons.

    Args:
        update:  Telegram Update object.
        context: PTB context carrying bot_data services and user_data state.
    """
    from services.user_registry import UserRegistry
    from services.gemini import GeminiService

    registry: UserRegistry = context.bot_data["registry"]
    gemini: GeminiService = context.bot_data["gemini"]
    sheets = context.bot_data["sheets"]

    tg_user = update.effective_user

    async with RequestTracer("voice_expense", user_id=tg_user.id) as tracer:
        with tracer.step("user_lookup"):
            user = await registry.get_user(tg_user.id)
        if user is None:
            await update.message.reply_text(
                "You are not registered yet. Send /start to sign up."
            )
            return

        with tracer.step("categories_fetch"):
            categories = sheets.get_categories(user.spreadsheet_id)

        # ── 1. Download audio ───────────────────────────────────────────────
        status_msg = await update.message.reply_text("Processing your voice message…")
        try:
            with tracer.step("audio_download"):
                voice = update.message.voice
                tg_file = await voice.get_file()
                audio_bytes: bytes = await tg_file.download_as_bytearray()
        except Exception as exc:
            logger.exception("Failed to download voice file for user %s: %s", tg_user.id, exc)
            await status_msg.edit_text("Could not download your voice message. Please try again.")
            return

        # ── 2. Parse with Gemini ────────────────────────────────────────────
        try:
            with tracer.step("gemini_parse"):
                expense = await gemini.parse_audio(audio_bytes, user.default_currency, categories)
        except Exception as exc:
            logger.exception("Gemini parsing failed for user %s: %s", tg_user.id, exc)
            await status_msg.edit_text(
                "Sorry, I couldn't understand the expense. "
                "Please try again or type it manually."
            )
            return

        # ── 3. Convert, save, alert ─────────────────────────────────────────
        raw_transcript = getattr(expense, "_raw_transcript", "")
        record, text, keyboard = await save_expense(
            context,
            user,
            amount=expense.amount,
            currency=expense.currency,
            category=expense.category,
            subcategory=expense.subcategory,
            description=expense.description,
            source=ExpenseSource.voice,
            raw_input=raw_transcript,
            tracer=tracer,
        )

        # ── 4. Show saved card ──────────────────────────────────────────────
        with tracer.step("send_confirmation"):
            await status_msg.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
