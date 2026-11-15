"""Per-user, timezone-aware "today" / "now" helpers.

Cloud Functions run in UTC, but every calendar decision the bot makes (what
"today" is, where a week or month starts, the spending pace, which recurring
expenses are due, which day an expense belongs to) has to follow the *user's*
wall clock. All of that goes through this module instead of bare
``date.today()`` / ``datetime.now()`` / ``datetime.utcnow()``.

Timezone resolution (``get_user_timezone``):

1. ``User.timezone`` — a bot setting stored next to the other user settings
   (``users/{telegram_id}.timezone`` in Firestore, ``timezone`` column of the
   Registry sheet), changed via ``/settings timezone <Area/City>`` or
   ``PUT /api/settings``. Empty means "use the default".
2. ``TIMEZONE`` env var (deployment default).
3. ``Asia/Bangkok`` when ``TIMEZONE`` is unset.

An invalid value at any level falls through to the next one (and finally to
UTC if even ``TIMEZONE`` is invalid), with a warning in the log.

The global-default helpers (``today()`` / ``now()`` without a user) are only
for places that genuinely have no user; the crons resolve each user's zone.

Persistence convention:

* Datetimes are stored **tz-aware in UTC** (``utc_now()``). Firestore keeps the
  instant; Sheets keeps an ISO string with ``+00:00``.
* Legacy *naive* datetimes (written by ``datetime.utcnow()`` before this
  change) are read as UTC via ``ensure_aware_utc``, so old data stays valid.
* The calendar day of a stored datetime is always computed in the user's zone
  (``local_date``), never with a bare ``.date()``.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, time, timezone, tzinfo
from functools import lru_cache
from typing import Any, Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Asia/Bangkok"

TzLike = Union[tzinfo, str, None, Any]  # Any: an object with a ``timezone`` attribute (User)


@lru_cache(maxsize=None)
def _load_zone(name: str) -> Optional[tzinfo]:
    """Return ZoneInfo for an IANA name, or None when it is not a valid zone."""
    if not name or name != name.strip():
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        logger.warning("Unknown timezone %r: %s", name, exc)
        return None


def is_valid_timezone(name: Optional[str]) -> bool:
    """True when ``name`` is a loadable IANA timezone (e.g. ``Europe/Kyiv``)."""
    return bool(name) and _load_zone(str(name)) is not None


def default_timezone_name() -> str:
    """Deployment default zone name: ``TIMEZONE`` env var, else ``Asia/Bangkok``."""
    return (os.environ.get("TIMEZONE") or "").strip() or DEFAULT_TIMEZONE


def default_tz() -> tzinfo:
    """Deployment default timezone; UTC (with a warning) if ``TIMEZONE`` is invalid."""
    name = default_timezone_name()
    zone = _load_zone(name)
    if zone is None:
        _warn_default_fallback(name)
        return timezone.utc
    return zone


@lru_cache(maxsize=None)
def _warn_default_fallback(name: str) -> None:
    logger.warning("Invalid TIMEZONE %r — falling back to UTC", name)


# Backward-compatible alias.
local_tz = default_tz


def resolve_timezone(name: Optional[str]) -> tzinfo:
    """Zone for ``name``; the deployment default when it is empty or invalid."""
    if name:
        zone = _load_zone(str(name))
        if zone is not None:
            return zone
    return default_tz()


def get_user_timezone(user: Any) -> tzinfo:
    """Resolve a user's timezone from their ``timezone`` bot setting (with defaults)."""
    return resolve_timezone(getattr(user, "timezone", None) if user is not None else None)


def user_timezone_name(user: Any) -> str:
    """Effective IANA name for display (settings screens)."""
    tz = get_user_timezone(user)
    return getattr(tz, "key", None) or str(tz)


def _as_tz(tz: TzLike) -> tzinfo:
    if tz is None:
        return default_tz()
    if isinstance(tz, tzinfo):
        return tz
    if isinstance(tz, str):
        return resolve_timezone(tz)
    return get_user_timezone(tz)


def _utc_now() -> datetime:
    """Current aware UTC time. Single seam for tests to freeze the clock."""
    return datetime.now(timezone.utc)


def utc_now() -> datetime:
    """Current time, tz-aware UTC — the storage format for new datetimes."""
    return _utc_now()


def user_now(tz: TzLike = None) -> datetime:
    """Current aware datetime in a user's zone (pass a User, tzinfo or IANA name)."""
    return _utc_now().astimezone(_as_tz(tz))


def user_today(tz: TzLike = None) -> date:
    """Current calendar date in a user's zone (pass a User, tzinfo or IANA name)."""
    return user_now(tz).date()


def now() -> datetime:
    """Current aware datetime in the deployment default zone (no user available)."""
    return user_now(None)


def today() -> date:
    """Current date in the deployment default zone (no user available)."""
    return user_today(None)


def ensure_aware_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC (legacy storage) and normalise aware ones to UTC."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_user_time(value: datetime, tz: TzLike = None) -> datetime:
    """Convert a stored datetime (aware or legacy naive UTC) into a user's zone."""
    return ensure_aware_utc(value).astimezone(_as_tz(tz))


def local_date(value: datetime, tz: TzLike = None) -> date:
    """Calendar day of a stored datetime in a user's zone."""
    return to_user_time(value, tz).date()


def start_of_day(day: date, tz: TzLike = None) -> datetime:
    """Local midnight of ``day`` in a user's zone, as an aware UTC datetime."""
    return datetime.combine(day, time.min, tzinfo=_as_tz(tz)).astimezone(timezone.utc)
