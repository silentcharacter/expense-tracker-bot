"""Shared fixtures for all tests."""

import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TEST_CONFIG_PATH = Path(__file__).resolve().parent / "test_config.yaml"
_ENV_YAML_PATH = Path(__file__).resolve().parent.parent / ".env.yaml"


def _load_test_config() -> None:
    """Merge .env.yaml and test_config.yaml into os.environ.

    Load order:
      1. .env.yaml  — provides API keys (GOOGLE_API_KEY, EXCHANGE_RATE_API_KEY, …)
      2. test_config.yaml — overrides infra settings (emulator host, storage backend, …)

    test_config.yaml always wins so prod Firestore / other infra is never used in tests.
    """
    for path, force in [(_ENV_YAML_PATH, False), (_TEST_CONFIG_PATH, True)]:
        if not path.exists():
            continue
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if value is None or not str(value).strip():
                continue
            if force:
                os.environ[key] = str(value)
            else:
                os.environ.setdefault(key, str(value))


@pytest.fixture(scope="session", autouse=True)
def _env() -> None:
    """Load test config once per session."""
    _load_test_config()


@pytest.fixture(scope="session")
def gemini_service():
    """Provide a real GeminiService backed by GOOGLE_API_KEY."""
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set in tests/test_config.yaml")
    from services.gemini import GeminiService
    return GeminiService()


@pytest.fixture
def currency_service():
    """Provide a real CurrencyService with a clean cache."""
    if not os.environ.get("EXCHANGE_RATE_API_KEY"):
        pytest.skip("EXCHANGE_RATE_API_KEY not set in tests/test_config.yaml")
    from services.currency import CurrencyService, _rate_cache
    _rate_cache.clear()
    return CurrencyService()


@pytest.fixture(scope="session")
def firestore_service():
    """Provide a FirestoreService backed by the local Firestore emulator."""
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("FIRESTORE_EMULATOR_HOST not set — start the Firestore emulator first")
    from services.firestore_service import FirestoreService
    return FirestoreService()
