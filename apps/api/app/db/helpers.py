"""Shared model helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class TZDateTime(TypeDecorator):
    """Timezone-aware UTC datetime storage.

    PostgreSQL stores real ``timestamptz``. SQLite has no timezone type and
    returns naive datetimes; this decorator coerces everything to UTC-aware on
    the way in and out so comparisons never mix naive and aware values.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value
