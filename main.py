"""Cloud Function entry point — Telegram webhook handler.

Receives Telegram webhook POST requests via functions-framework, routes
each Update to the appropriate handler, and returns HTTP 200.

Deploy command:
  gcloud functions deploy expense-bot \
    --gen2 --runtime=python312 --region=asia-southeast1 \
    --source=. --entry-point=webhook --trigger-http \
    --allow-unauthenticated --env-vars-file=.env.yaml --memory=256MB --timeout=60s
"""

import asyncio
import logging
import os
from typing import Optional

import functions_framework
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from handlers import commands, voice, text, callbacks
from services.gemini import GeminiService
from services.sheets import SheetsService
from services.currency import CurrencyService
from services.user_registry import UserRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Singleton Application (reused across warm invocations) ───────────────────
_app: Optional[Application] = None


def _build_application() -> Application:
    """Construct and configure the PTB Application with all handlers."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()

    # ── Shared services ─────────────────────────────────────────────────────
    app.bot_data["gemini"] = GeminiService()
    app.bot_data["sheets"] = SheetsService()
    app.bot_data["currency"] = CurrencyService()
    app.bot_data["registry"] = UserRegistry(
        sheets_service=app.bot_data["sheets"]
    )

    # ── Command handlers ────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CommandHandler("email", commands.email))
    app.add_handler(CommandHandler("settings", commands.settings))
    app.add_handler(CommandHandler("today", commands.today))
    app.add_handler(CommandHandler("week", commands.week))
    app.add_handler(CommandHandler("month", commands.month))
    app.add_handler(CommandHandler("last", commands.last))
    app.add_handler(CommandHandler("undo", commands.undo))
    app.add_handler(CommandHandler("budget", commands.budget))
    app.add_handler(CommandHandler("export", commands.export))
    app.add_handler(CommandHandler("cat", commands.cat))

    # ── Message handlers ────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.VOICE, voice.handle_voice))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text.handle_text)
    )

    # ── Inline button callbacks ─────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callbacks.handle_callback))

    logger.info("Application built successfully.")
    return app


def _get_app() -> Application:
    """Return the singleton Application, building it on first call."""
    global _app
    if _app is None:
        _app = _build_application()
    return _app


# ── Cloud Function entry point ───────────────────────────────────────────────

@functions_framework.http
def webhook(request) -> tuple[str, int]:
    """Receive a Telegram webhook POST and dispatch it to the appropriate handler.

    Args:
        request: Flask/WSGI request object provided by functions-framework.

    Returns:
        ("ok", 200) on success, or an error message with a non-200 status.
    """
    # Optional: verify Telegram secret token header
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if secret:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming != secret:
            logger.warning("Invalid webhook secret token.")
            return "Forbidden", 403

    payload = request.get_json(silent=True)
    if not payload:
        logger.warning("Empty or non-JSON request body.")
        return "Bad Request", 400

    app = _get_app()

    try:
        update = Update.de_json(payload, app.bot)
    except Exception as exc:
        logger.error("Failed to deserialise Update: %s", exc)
        return "Bad Request", 400

    # Run the async update processing in a fresh event loop.
    # Cloud Functions run each invocation in a thread with its own loop.
    try:
        asyncio.run(_process_update(app, update))
    except Exception as exc:
        logger.exception("Unhandled error processing update %s: %s", update.update_id, exc)
        # Return 200 to prevent Telegram from retrying indefinitely.
        return "Internal error (logged)", 200

    return "ok", 200


async def _process_update(app: Application, update: Update) -> None:
    """Initialise the application (if needed) and process one Update.

    Args:
        app:    The PTB Application instance.
        update: The deserialized Telegram Update.
    """
    async with app:
        await app.process_update(update)
