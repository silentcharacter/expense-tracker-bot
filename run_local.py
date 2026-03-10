"""Run the bot locally in polling mode with env vars loaded from .env.yaml."""

import os
import sys
from pathlib import Path

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


def main() -> None:
    _load_env_yaml()
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

    from main import _build_application

    app = _build_application()
    print("Bot started in polling mode. Press Ctrl+C to stop.")
    print("Don't forget to delete the webhook first:")
    print(f"  curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/deleteWebhook")
    print()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
