"""Run the bot locally in polling mode with env vars loaded from .env.yaml."""

import os
import sys
from pathlib import Path
from urllib.request import urlopen

import yaml


def _load_env_yaml(path: Path = Path(".env.yaml")) -> None:
    """Parse .env.yaml and inject values into os.environ."""
    if not path.exists():
        print(f"Error: {path} not found. Copy from .env.yaml.example and fill in values.")
        sys.exit(1)
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(f"Error: {path} is not a valid YAML mapping.")
        sys.exit(1)
    for key, value in data.items():
        if value is not None:
            os.environ.setdefault(key, str(value))


def _delete_webhook(token: str) -> None:
    """Delete the Telegram webhook so polling works."""
    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    try:
        with urlopen(url) as resp:
            body = resp.read().decode()
        print(f"Webhook deleted: {body}")
    except Exception as exc:
        print(f"Warning: failed to delete webhook: {exc}")


def main() -> None:
    _load_env_yaml()
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

    _delete_webhook(os.environ["TELEGRAM_BOT_TOKEN"])

    from main import _build_application

    app = _build_application()
    print("Bot started in polling mode. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
