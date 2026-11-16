"""Tests for Telegram webhook secret_token verification in main.webhook."""

from unittest.mock import MagicMock, patch

import flask
import pytest

import main

SECRET = "test_secret-ABC123"
HEADER = main.WEBHOOK_SECRET_HEADER
UPDATE = {"update_id": 1}

_flask_app = flask.Flask(__name__)


def _call(path: str = "/", headers: dict | None = None, json: dict | None = UPDATE):
    """Invoke main.webhook inside a Flask request context, with update
    processing mocked out. Returns (status_code, processed: bool)."""
    with (
        _flask_app.test_request_context(
            path, method="POST", json=json, headers=headers or {}
        ),
        patch.object(main, "_get_app", return_value=MagicMock()),
        patch.object(main.Update, "de_json", return_value=MagicMock(update_id=1)),
        patch.object(main, "_process_update", new=MagicMock()) as process,
        patch.object(main.asyncio, "run") as run,
    ):
        result = main.webhook(flask.request)
        processed = run.called and process.called
    status = result[1] if isinstance(result, tuple) else 200
    return status, processed


@pytest.fixture
def secret_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)


def test_valid_secret_is_accepted(secret_env) -> None:
    status, processed = _call(headers={HEADER: SECRET})
    assert status == 200
    assert processed


def test_wrong_secret_is_rejected(secret_env) -> None:
    status, processed = _call(headers={HEADER: SECRET + "x"})
    assert status == 403
    assert not processed


def test_missing_header_is_rejected(secret_env) -> None:
    status, processed = _call()
    assert status == 403
    assert not processed


def test_unset_secret_allows_and_warns(monkeypatch, caplog) -> None:
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(main, "_warned_missing_webhook_secret", False)
    with caplog.at_level("WARNING", logger="main"):
        status, processed = _call()
    assert status == 200
    assert processed
    assert "TELEGRAM_WEBHOOK_SECRET is not set" in caplog.text


def test_empty_secret_treated_as_unset(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    status, processed = _call()
    assert status == 200
    assert processed


def test_api_routes_not_gated_by_webhook_secret(secret_env) -> None:
    """/api/* uses Telegram initData auth, not the webhook secret."""
    with (
        _flask_app.test_request_context("/api/summary", method="GET"),
        patch.object(main, "_handle_api_route", return_value=("ok", 200)) as api,
    ):
        result = main.webhook(flask.request)
    assert result == ("ok", 200)
    api.assert_called_once()


def test_cron_routes_not_gated_by_webhook_secret(secret_env, monkeypatch) -> None:
    """/cron/* uses X-Cron-Secret; webhook secret header is irrelevant."""
    monkeypatch.setenv("CRON_SECRET", "cron-s3cret")
    with _flask_app.test_request_context(
        "/cron/unknown", method="POST", headers={"X-Cron-Secret": "wrong"}
    ):
        result = main.webhook(flask.request)
    assert result[1] == 403
    with _flask_app.test_request_context(
        "/cron/unknown", method="POST", headers={"X-Cron-Secret": "cron-s3cret"}
    ):
        result = main.webhook(flask.request)
    assert result[1] == 404


def test_httpx_request_logging_suppressed() -> None:
    """httpx INFO logs include the full URL, i.e. the bot token."""
    import logging

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
