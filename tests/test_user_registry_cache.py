"""Unit tests for the shared UserRegistry singleton and its TTL cache."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.expense import User, UserRole, UserStatus
from services import user_registry
from services.user_registry import (
    CACHE_TTL_SECONDS,
    UserRegistry,
    get_registry,
    reset_registry_for_tests,
)


def _user(**kw) -> User:
    d = {
        "telegram_id": 1,
        "display_name": "A",
        "spreadsheet_id": "1",
        "base_currency": "USD",
        "default_currency": "USD",
        "role": UserRole.user,
        "status": UserStatus.active,
        "created_at": datetime(2026, 1, 1),
    }
    d.update(kw)
    return User(**d)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    c = _Clock()
    with patch.object(user_registry, "_monotonic", c):
        yield c


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def _registry() -> tuple[UserRegistry, MagicMock]:
    storage = MagicMock()
    storage.find_user.return_value = _user()
    return UserRegistry(sheets_service=storage), storage


def test_ttl_constant():
    assert CACHE_TTL_SECONDS == 45


def test_singleton_shared_between_bot_and_api():
    bot_side = get_registry(MagicMock())
    api_side = get_registry(MagicMock())
    assert bot_side is api_side
    from api import routes

    with patch("api.routes.get_storage", return_value=MagicMock()):
        assert routes._get_registry() is bot_side


async def test_unexpired_cache_does_not_reread(clock):
    reg, storage = _registry()
    await reg.get_user(1)
    clock.now += CACHE_TTL_SECONDS - 1
    await reg.get_user(1)
    assert storage.find_user.call_count == 1


async def test_expired_cache_rereads(clock):
    reg, storage = _registry()
    await reg.get_user(1)
    clock.now += CACHE_TTL_SECONDS + 1
    storage.find_user.return_value = _user(active_trip_id="trip1234")
    user = await reg.get_user(1)
    assert storage.find_user.call_count == 2
    assert user.active_trip_id == "trip1234"


async def test_invalidate_user_forces_reread(clock):
    reg, storage = _registry()
    await reg.get_user(1)
    storage.find_user.return_value = _user(active_trip_id="abcd1234")
    reg.invalidate_user(1)
    assert (await reg.get_user(1)).active_trip_id == "abcd1234"


async def test_module_invalidate_user_hits_singleton(clock):
    storage = MagicMock()
    storage.find_user.return_value = _user()
    reg = get_registry(storage)
    await reg.get_user(1)
    storage.find_user.return_value = _user(active_trip_id="zzzz9999")
    user_registry.invalidate_user(1)
    assert (await reg.get_user(1)).active_trip_id == "zzzz9999"


def test_module_invalidate_without_singleton_is_noop():
    user_registry.invalidate_user(1)  # must not raise or create a registry
    assert user_registry._registry is None


async def test_cache_user_resets_ttl(clock):
    reg, storage = _registry()
    await reg.get_user(1)
    clock.now += CACHE_TTL_SECONDS - 1
    reg.cache_user(_user(active_trip_id="fresh000"))
    clock.now += CACHE_TTL_SECONDS - 1
    assert (await reg.get_user(1)).active_trip_id == "fresh000"
    assert storage.find_user.call_count == 1


async def test_update_settings_updates_cache_and_ttl(clock):
    reg, storage = _registry()
    await reg.get_user(1)
    clock.now += CACHE_TTL_SECONDS - 1
    updated = await reg.update_settings(1, base_currency="EUR")
    clock.now += CACHE_TTL_SECONDS - 1  # would be expired without the TTL reset
    assert (await reg.get_user(1)) is updated
    assert updated.base_currency == "EUR"
    assert storage.find_user.call_count == 1


async def test_set_quick_expenses_and_keyboard_update_cache(clock):
    reg, storage = _registry()
    storage.set_quick_expenses.return_value = True
    storage.set_quick_keyboard_hidden.return_value = True
    await reg.set_quick_expenses(1, [])
    hidden = await reg.set_quick_keyboard_hidden(1, True)
    assert (await reg.get_user(1)) is hidden
    assert hidden.quick_keyboard_hidden is True


async def test_transfer_to_user_updates_cache(monkeypatch, clock):
    monkeypatch.setenv("STORAGE_BACKEND", "firestore")
    reg, _storage = _registry()
    await reg.transfer_to_user(1, "a@example.com")
    assert (await reg.get_user(1)).email == "a@example.com"


async def test_refresh_user_bypasses_cache_and_stores(clock):
    reg, storage = _registry()
    await reg.get_user(1)
    storage.find_user.return_value = _user(active_trip_id="newtrip1")
    assert (await reg.refresh_user(1)).active_trip_id == "newtrip1"
    assert (await reg.get_user(1)).active_trip_id == "newtrip1"
    assert storage.find_user.call_count == 2


async def test_get_all_active_users_populates_cache(clock):
    reg, storage = _registry()
    storage.get_all_active_users.return_value = [_user(telegram_id=7)]
    await reg.get_all_active_users()
    storage.find_user.reset_mock()
    assert (await reg.get_user(7)).telegram_id == 7
    storage.find_user.assert_not_called()


async def test_create_user_caches(monkeypatch, clock):
    monkeypatch.setenv("STORAGE_BACKEND", "firestore")
    reg, storage = _registry()
    user = await reg.create_user(5, "u", "U", "USD", "USD")
    storage.find_user.reset_mock()
    assert (await reg.get_user(5)) is user
    storage.find_user.assert_not_called()
