"""Voice message handler: OGG → Gemini → Expense confirmation."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from models.expense import ExpenseRecord, ExpenseSource
from models.category import category_label, subcategory_label
from handlers.callbacks import saved_keyboard, _format_confirmation

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
    from services.currency import CurrencyService
    from services.sheets import SheetsService

    registry: UserRegistry = context.bot_data["registry"]
    gemini: GeminiService = context.bot_data["gemini"]
    currency_svc: CurrencyService = context.bot_data["currency"]
    sheets: SheetsService = context.bot_data["sheets"]

    tg_user = update.effective_user
    user = await registry.get_user(tg_user.id)
    if user is None:
        await update.message.reply_text(
            "You are not registered yet. Send /start to sign up."
        )
        return

    categories = sheets.get_categories(user.spreadsheet_id)

    # ── 1. Download audio ───────────────────────────────────────────────────
    status_msg = await update.message.reply_text("Processing your voice message…")
    try:
        voice = update.message.voice
        tg_file = await voice.get_file()
        audio_bytes: bytes = await tg_file.download_as_bytearray()
    except Exception as exc:
        logger.exception("Failed to download voice file for user %s: %s", tg_user.id, exc)
        await status_msg.edit_text("Could not download your voice message. Please try again.")
        return

    # ── 2. Parse with Gemini ────────────────────────────────────────────────
    try:
        expense = await gemini.parse_audio(audio_bytes, user.default_currency, categories)
    except Exception as exc:
        logger.exception("Gemini parsing failed for user %s: %s", tg_user.id, exc)
        await status_msg.edit_text(
            "Sorry, I couldn't understand the expense. "
            "Please try again or type it manually."
        )
        return

    # ── 3. Convert currency ─────────────────────────────────────────────────
    try:
        amount_base, fx_rate = await currency_svc.convert(
            expense.amount, expense.currency, user.base_currency
        )
    except Exception as exc:
        logger.exception("Currency conversion failed for %s→%s: %s", expense.currency, user.base_currency, exc)
        # Fall back to treating the amount as already in base currency
        amount_base = expense.amount
        fx_rate = 1.0

    # ── 4. Build pending record ─────────────────────────────────────────────
    raw_transcript = getattr(expense, "_raw_transcript", "")
    record = ExpenseRecord(
        amount_local=expense.amount,
        local_currency=expense.currency,
        amount_base=amount_base,
        base_currency=user.base_currency,
        fx_rate=fx_rate,
        category=expense.category,
        subcategory=expense.subcategory,
        description=expense.description,
        source=ExpenseSource.voice,
        raw_input=raw_transcript,
    )

    # ── 5. Save immediately ─────────────────────────────────────────────────
    sheets.append_transaction(user.spreadsheet_id, record)
    context.user_data["last_expense"] = {"record": record}

    # ── 6. Show saved card ──────────────────────────────────────────────────
    cat_label = category_label(record.category)
    sub_label = subcategory_label(record.category, record.subcategory) if record.subcategory else ""
    cat_display = f"{cat_label} / {sub_label}" if sub_label else cat_label

    text = (
        f"{_format_confirmation(record, user.base_currency, cat_display)}\n\n"
        f"✓ Saved"
    )
    await status_msg.edit_text(
        text,
        reply_markup=saved_keyboard(record.id),
        parse_mode="Markdown",
    )
