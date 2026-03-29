"""Unit tests for services/auth.py — no external services required."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from services.auth import validate_init_data

BOT_TOKEN = "123456789:test_token_for_unit_tests"

TEST_USER = {"id": 42, "first_name": "Alice", "username": "alice"}


def make_init_data(
    bot_token: str,
    user: dict = TEST_USER,
    auth_date: int | None = None,
    tamper_hash: bool = False,
    include_hash: bool = True,
    include_auth_date: bool = True,
) -> str:
    """Build a signed initData string for testing."""
    if auth_date is None:
        auth_date = int(time.time())

    params: dict[str, str] = {"query_id": "AAHtest"}
    if include_auth_date:
        params["auth_date"] = str(auth_date)
    params["user"] = json.dumps(user)

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if tamper_hash:
        computed_hash = "00000000" + computed_hash[8:]

    if include_hash:
        params["hash"] = computed_hash

    return urlencode(params)


def test_valid_init_data() -> None:
    """Valid initData with current auth_date returns user dict."""
    init_data = make_init_data(BOT_TOKEN)
    result = validate_init_data(init_data, BOT_TOKEN)
    assert result is not None
    assert result["id"] == TEST_USER["id"]
    assert result["first_name"] == TEST_USER["first_name"]


def test_expired_init_data() -> None:
    """initData older than 1 hour is rejected."""
    old_auth_date = int(time.time()) - 7200  # 2 hours ago
    init_data = make_init_data(BOT_TOKEN, auth_date=old_auth_date)
    assert validate_init_data(init_data, BOT_TOKEN) is None


def test_tampered_hash() -> None:
    """initData with a corrupted hash is rejected."""
    init_data = make_init_data(BOT_TOKEN, tamper_hash=True)
    assert validate_init_data(init_data, BOT_TOKEN) is None


def test_wrong_bot_token() -> None:
    """Valid initData validated with the wrong bot token is rejected."""
    init_data = make_init_data(BOT_TOKEN)
    assert validate_init_data(init_data, "999999999:wrong_token") is None


def test_missing_hash() -> None:
    """initData without a hash field is rejected."""
    init_data = make_init_data(BOT_TOKEN, include_hash=False)
    assert validate_init_data(init_data, BOT_TOKEN) is None


def test_missing_auth_date() -> None:
    """initData without auth_date is rejected (treated as epoch = expired)."""
    init_data = make_init_data(BOT_TOKEN, include_auth_date=False)
    assert validate_init_data(init_data, BOT_TOKEN) is None
