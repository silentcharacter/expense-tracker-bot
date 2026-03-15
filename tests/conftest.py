"""Shared fixtures for integration tests."""

import os
import sys
from pathlib import Path

import pytest
import yaml

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_env_yaml() -> None:
    """Load .env.yaml into os.environ so services can read their keys."""
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env.yaml"
    if not env_path.exists():
        pytest.skip(".env.yaml not found — cannot run integration tests")
    with open(env_path) as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict):
        for key, value in data.items():
            if value is not None:
                os.environ.setdefault(key, str(value))

    sa_file = project_root / "credentials.json"
    if sa_file.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(sa_file))


@pytest.fixture(scope="session", autouse=True)
def _env():
    """Ensure env vars are loaded once per test session."""
    _load_env_yaml()


@pytest.fixture(scope="session")
def gemini_service():
    """Provide a real GeminiService instance backed by .env.yaml API key."""
    from services.gemini import GeminiService
    return GeminiService()


@pytest.fixture
def currency_service():
    """Provide a real CurrencyService instance with a clean cache."""
    from services.currency import CurrencyService, _rate_cache
    _rate_cache.clear()
    return CurrencyService()


@pytest.fixture(scope="session")
def sheets_service():
    """Provide a real SheetsService instance backed by .env.yaml credentials."""
    from services.sheets import SheetsService
    return SheetsService()
