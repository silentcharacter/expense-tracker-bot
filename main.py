"""Cloud Function entry point — Telegram webhook handler.

Receives Telegram webhook POST requests via functions-framework, routes
each Update to the appropriate handler, and returns HTTP 200.

Deploy command:
  gcloud functions deploy expense-bot \
    --gen2 --runtime=python312 --region=asia-southeast1 \
    --source=. --entry-point=webhook --trigger-http \
    --allow-unauthenticated --env-vars-file=.env.yaml --memory=256MB --timeout=60s --service-account=expense-bot-sa@expense-bot-489609.iam.gserviceaccount.com
"""

import asyncio
import logging
import os
from typing import Optional

import functions_framework
from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from models.expense import UserRole

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

# ── Bot command menu ──────────────────────────────────────────────────────────

_PUBLIC_COMMANDS = [
    BotCommand("start", "Register or view your profile"),
    BotCommand("last", "Recent transactions"),
    BotCommand("undo", "Delete last transaction"),
    BotCommand("export", "Export CSV"),
    BotCommand("settings", "Currency settings"),
    BotCommand("email", "Share spreadsheet"),
    BotCommand("feedback", "Send feedback"),
]

_ADMIN_COMMANDS = _PUBLIC_COMMANDS + [
    BotCommand("broadcast", "Send message to all users"),
]

_commands_registered = False

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
    app.bot_data["sheets"].ensure_registry_header()

    # ── Command handlers ────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CommandHandler("email", commands.email))
    app.add_handler(CommandHandler("settings", commands.settings))
    app.add_handler(CommandHandler("last", commands.last))
    app.add_handler(CommandHandler("undo", commands.undo))
    app.add_handler(CommandHandler("export", commands.export))
    app.add_handler(CommandHandler("feedback", commands.feedback))
    app.add_handler(CommandHandler("broadcast", commands.broadcast))

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


# ── CORS helpers ─────────────────────────────────────────────────────────────


def _cors_preflight() -> tuple:
    """Return a CORS preflight response (204 No Content)."""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }
    return "", 204, headers


def _handle_cron_route(request, path: str):
    """Authenticate and dispatch /cron/* invocations from Cloud Scheduler.

    Authentication: a shared secret in the ``X-Cron-Secret`` header that must
    match the ``CRON_SECRET`` env var. If ``CRON_SECRET`` is unset the route
    returns 503 — fail-closed rather than running unauthenticated.
    """
    from flask import jsonify as _jsonify

    expected = os.environ.get("CRON_SECRET", "")
    if not expected:
        return _jsonify({"error": "cron disabled"}), 503
    if request.headers.get("X-Cron-Secret", "") != expected:
        return _jsonify({"error": "forbidden"}), 403

    if path == "/cron/recurring":
        from jobs.recurring_cron import run_recurring_cron
        try:
            summary = asyncio.run(run_recurring_cron())
        except Exception as exc:
            logger.exception("Recurring cron failed: %s", exc)
            return _jsonify({"error": "internal error"}), 500
        return _jsonify(summary), 200

    if path == "/cron/weekly_summary":
        from jobs.weekly_summary_cron import run_weekly_summary
        try:
            summary = asyncio.run(run_weekly_summary())
        except Exception as exc:
            logger.exception("Weekly summary cron failed: %s", exc)
            return _jsonify({"error": "internal error"}), 500
        return _jsonify(summary), 200

    return _jsonify({"error": "not found"}), 404


def _handle_api_route(request):
    """Run the async Mini App API handler and add CORS headers to the response."""
    from api.routes import handle_api_request
    from flask import jsonify as _jsonify

    try:
        result = asyncio.run(handle_api_request(request))
    except Exception as exc:
        logger.exception("Mini App API handler error: %s", exc)
        return _jsonify({"error": "internal server error"}), 500

    # CORS preflight returns a 3-tuple ("", 204, headers_dict)
    if isinstance(result, tuple) and len(result) == 3:
        return result

    body, status = result[0], result[1]
    if hasattr(body, "headers"):
        body.headers["Access-Control-Allow-Origin"] = "*"
    return body, status


# ── Cloud Function entry point ───────────────────────────────────────────────

@functions_framework.http
def webhook(request) -> tuple:
    """Receive requests and route them to the Telegram webhook or Mini App API.

    Args:
        request: Flask/WSGI request object provided by functions-framework.

    Returns:
        HTTP response tuple.
    """
    path = request.path

    # CORS preflight — must be handled before any auth checks
    if request.method == "OPTIONS":
        return _cors_preflight()

    # Mini App REST API — uses its own initData auth, not the webhook secret
    if path.startswith("/api/"):
        return _handle_api_route(request)

    # Cron-triggered jobs (Cloud Scheduler) — authenticated via shared secret header
    if path.startswith("/cron/"):
        return _handle_cron_route(request, path)

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
        await _register_commands_once(app)
        await app.process_update(update)


async def _register_commands_once(app: Application) -> None:
    """Set the bot command menu on first invocation after cold start."""
    global _commands_registered
    if _commands_registered:
        return
    _commands_registered = True

    try:
        await app.bot.set_my_commands(_PUBLIC_COMMANDS)

        registry = app.bot_data.get("registry")
        if registry:
            users = await registry.get_all_active_users()
            for user in users:
                if user.role == UserRole.admin:
                    await app.bot.set_my_commands(
                        _ADMIN_COMMANDS,
                        scope=BotCommandScopeChat(chat_id=user.telegram_id),
                    )
    except Exception as exc:
        logger.warning("Failed to register bot commands: %s", exc)
