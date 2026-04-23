"""Shared fixtures for all tests."""

import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TEST_CONFIG_PATH = Path(__file__).resolve().parent / "test_config.yaml"


def _load_test_config() -> None:
    """Load tests/test_config.yaml into os.environ. Pre-set vars take priority."""
    if not _TEST_CONFIG_PATH.exists():
        return
    with open(_TEST_CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict):
        for key, value in data.items():
            if value is not None and str(value).strip():
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
