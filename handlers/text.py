"""Text message handler: plain text → Gemini → Expense confirmation."""

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from models.expense import ExpenseRecord, ExpenseSource
from models.category import category_label, subcategory_label
from handlers.callbacks import saved_keyboard, _format_confirmation, currency_keyboard, CB_ONBOARD_BASE
from services.tracing import RequestTracer

logger = logging.getLogger(__name__)

# Patterns that look like commands or non-expense text
_COMMAND_RE = re.compile(r"^/")
# Minimum plausible expense: at least one digit
_HAS_DIGIT_RE = re.compile(r"\d")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process an incoming text message that may be an expense entry.

    Also handles free-text responses during onboarding (currency input).

    Flow:
      1. Skip commands and messages with no digits.
      2. Handle "awaiting" state for onboarding / settings currency input.
      3. Retrieve registered user; prompt /start if absent.
      4. Send text to Gemini for parsing.
      5. Fetch FX rate and compute amount_base.
      6. Present a confirmation card with inline buttons.

    Args:
        update:  Telegram Update object.
        context: PTB context carrying bot_data services and user_data state.
    """
    message = update.message
    text = (message.text or "").strip()

    # ── Handle awaiting states (onboarding / settings) ──────────────────────
    awaiting = context.user_data.get("awaiting")
    if awaiting:
        await _handle_awaiting_input(update, context, awaiting, text)
        return

    # ── Skip commands and non-expense text ─────────────────────────────────
    if _COMMAND_RE.match(text) or not _HAS_DIGIT_RE.search(text):
        return

    from services.user_registry import UserRegistry
    from services.gemini import GeminiService
    from services.currency import CurrencyService
    from services.sheets import SheetsService

    registry: UserRegistry = context.bot_data["registry"]
    gemini: GeminiService = context.bot_data["gemini"]
    currency_svc: CurrencyService = context.bot_data["currency"]
    sheets: SheetsService = context.bot_data["sheets"]

    tg_user = update.effective_user

    async with RequestTracer("text_expense", user_id=tg_user.id) as tracer:
        with tracer.step("user_lookup"):
            user = await registry.get_user(tg_user.id)
        if user is None:
            await message.reply_text(
                "You are not registered yet. Send /start to sign up."
            )
            return

        with tracer.step("categories_fetch"):
            categories = sheets.get_categories(user.spreadsheet_id)

        # ── Parse with Gemini ───────────────────────────────────────────────
        status_msg = await message.reply_text("Parsing…")
        try:
            with tracer.step("gemini_parse"):
                expense = await gemini.parse_text(text, user.default_currency, categories)
        except Exception as exc:
            logger.exception("Gemini text parsing failed for user %s: %s", tg_user.id, exc)
            await status_msg.edit_text(
                "Sorry, I couldn't parse that expense. "
                "Try: `350 baht taxi grab`",
                parse_mode="Markdown",
            )
            return

        # ── Currency conversion ─────────────────────────────────────────────
        try:
            with tracer.step("currency_convert"):
                amount_base, fx_rate = await currency_svc.convert(
                    expense.amount, expense.currency, user.base_currency
                )
        except Exception as exc:
            logger.exception("Currency conversion failed %s→%s: %s", expense.currency, user.base_currency, exc)
            amount_base = expense.amount
            fx_rate = 1.0

        # ── Build pending record ────────────────────────────────────────────
        record = ExpenseRecord(
            amount_local=expense.amount,
            local_currency=expense.currency,
            amount_base=amount_base,
            base_currency=user.base_currency,
            fx_rate=fx_rate,
            category=expense.category,
            subcategory=expense.subcategory,
            description=expense.description,
            source=ExpenseSource.text,
            raw_input=text,
        )
        # ── Save immediately ────────────────────────────────────────────────
        with tracer.step("sheets_write"):
            sheets.append_transaction(user.spreadsheet_id, record)
        context.user_data["last_expense"] = {"record": record}

        # ── Show saved card ─────────────────────────────────────────────────
        cat_label = category_label(record.category)
        sub_label = subcategory_label(record.category, record.subcategory) if record.subcategory else ""
        cat_display = f"{cat_label} / {sub_label}" if sub_label else cat_label

        confirmation = (
            f"{_format_confirmation(record, user.base_currency, cat_display)}\n\n"
            f"✓ Saved"
        )
        with tracer.step("send_confirmation"):
            await status_msg.edit_text(
                confirmation,
                reply_markup=saved_keyboard(record.id),
                parse_mode="Markdown",
            )


# ── Awaiting-state handler ───────────────────────────────────────────────────

async def _handle_awaiting_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    awaiting: str,
    text: str,
) -> None:
    """Handle free-text input during onboarding, /settings, or /email flows."""
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]

    if awaiting == "email_address":
        google_email = text.strip()
        if "@" not in google_email or "." not in google_email.split("@")[-1]:
            await update.message.reply_text(
                "That doesn't look like a valid email address. Please try again."
            )
            return
        context.user_data.pop("awaiting", None)
        await update.message.reply_text("Sharing your Spreadsheet…")
        try:
            await registry.transfer_to_user(update.effective_user.id, google_email)
        except Exception as exc:
            logger.exception(
                "Failed to transfer spreadsheet for %s: %s",
                update.effective_user.id,
                exc,
            )
            await update.message.reply_text(f"Error: {exc}")
            return
        await update.message.reply_text(
            f"Done! Your Spreadsheet has been shared with *{google_email}*.\n"
            "You can now find it in Google Drive.",
            parse_mode="Markdown",
        )
        return

    if awaiting.startswith("edit_description:"):
        record_id = awaiting.split(":", 1)[1]
        context.user_data.pop("awaiting", None)
        from services.sheets import SheetsService
        sheets: SheetsService = context.bot_data["sheets"]
        user = await registry.get_user(update.effective_user.id)
        if not user:
            await update.message.reply_text("User not found.")
            return
        ok = sheets.update_transaction_description(user.spreadsheet_id, record_id, text)
        if ok:
            last = context.user_data.get("last_expense", {})
            rec = last.get("record")
            if rec and rec.id == record_id:
                rec.description = text
            await update.message.reply_text(f"Description updated: {text}")
        else:
            await update.message.reply_text("Could not find the expense to update.")
        return

    if awaiting == "feedback_text":
        context.user_data.pop("awaiting", None)
        user = await registry.get_user(update.effective_user.id)
        if user:
            from services.sheets import SheetsService
            sheets: SheetsService = context.bot_data["sheets"]
            sheets.append_feedback(user.telegram_id, user.username, user.display_name, text)
            await update.message.reply_text("Thank you for your feedback!")
        else:
            await update.message.reply_text("You are not registered. Send /start first.")
        return

    code = text.strip().upper()

    if not registry.validate_currency(code):
        await update.message.reply_text(
            f"'{code}' is not a valid ISO 4217 currency code. "
            "Please enter a 3-letter code like USD, EUR, THB."
        )
        return

    context.user_data.pop("awaiting", None)

    if awaiting == "onboard_base_currency":
        context.user_data["onboard_base_currency"] = code
        from handlers.callbacks import currency_keyboard, CB_ONBOARD_DEFAULT
        await update.message.reply_text(
            f"Base currency: *{code}*\n\nNow choose your default currency:",
            parse_mode="Markdown",
            reply_markup=currency_keyboard(CB_ONBOARD_DEFAULT),
        )

    elif awaiting == "onboard_default_currency":
        base_currency = context.user_data.get("onboard_base_currency", "USD")
        from handlers.callbacks import _finish_onboarding
        # Temporarily attach a callback_query-like interface isn't possible here;
        # we call the underlying logic directly by replicating the finish logic.
        await _complete_onboarding_from_text(update, context, base_currency, code)

    elif awaiting == "settings_base_currency":
        user = await registry.get_user(update.effective_user.id)
        if user:
            try:
                updated = await registry.update_settings(
                    update.effective_user.id, code, user.default_currency
                )
                await update.message.reply_text(
                    f"Base currency updated to *{updated.base_currency}*.",
                    parse_mode="Markdown",
                )
            except ValueError as exc:
                await update.message.reply_text(str(exc))

    elif awaiting == "settings_default_currency":
        user = await registry.get_user(update.effective_user.id)
        if user:
            try:
                updated = await registry.update_settings(
                    update.effective_user.id, user.base_currency, code
                )
                await update.message.reply_text(
                    f"Default currency updated to *{updated.default_currency}*.",
                    parse_mode="Markdown",
                )
            except ValueError as exc:
                await update.message.reply_text(str(exc))



async def _complete_onboarding_from_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    base_currency: str,
    default_currency: str,
) -> None:
    """Finish onboarding when the user typed their default currency manually."""
    from services.user_registry import UserRegistry

    registry: UserRegistry = context.bot_data["registry"]
    tg_user = update.effective_user

    try:
        user = await registry.create_user(
            telegram_id=tg_user.id,
            username=tg_user.username or "",
            display_name=tg_user.full_name,
            base_currency=base_currency,
            default_currency=default_currency,
        )
    except Exception as exc:
        logger.exception("Onboarding failed for %s: %s", tg_user.id, exc)
        await update.message.reply_text(f"Registration failed: {exc}\nSend /start to retry.")
        return

    await update.message.reply_text(
        f"All set!\n\n"
        f"Base currency: *{user.base_currency}*\n"
        f"Default currency: *{user.default_currency}*\n\n"
        f"Send a voice message or type an expense to get started.\n"
        f"To link your Google Sheet, send /email your@gmail.com",
        parse_mode="Markdown",
    )
    context.user_data.pop("onboard_base_currency", None)
    context.user_data.pop("onboard_default_currency", None)
