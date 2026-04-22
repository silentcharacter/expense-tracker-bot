"""Telegram Mini App initData validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote


MAX_AUTH_AGE_SECONDS = 86400  # 24 hours (per Telegram recommendation)


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validate and parse Telegram Mini App initData.

    Returns user dict if valid, None if invalid or expired.

    Algorithm (per Telegram docs):
    1. Parse init_data as query string
    2. Extract 'hash' parameter, remove it from params
    3. Reject if auth_date is older than MAX_AUTH_AGE_SECONDS
    4. Sort remaining params alphabetically
    5. Build data_check_string: "key=value\\nkey=value\\n..."
    6. secret_key = HMAC-SHA256("WebAppData", bot_token)
    7. Compute HMAC-SHA256(secret_key, data_check_string)
    8. Compare with received hash using constant-time comparison
    """
    try:
        parsed = parse_qs(init_data)
    except Exception:
        return None

    if "hash" not in parsed:
        return None

    received_hash = parsed.pop("hash")[0]

    auth_date = int(parsed.get("auth_date", ["0"])[0])
    if time.time() - auth_date > MAX_AUTH_AGE_SECONDS:
        return None

    data_check_string = "\n".join(
        f"{k}={v[0]}" for k, v in sorted(parsed.items())
    )

    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    user_json = parsed.get("user", ["{}"])[0]
    return json.loads(unquote(user_json))
