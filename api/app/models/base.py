from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime
from sqlmodel import Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def created_at_field() -> Any:
    return Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


def nullable_ts_field() -> Any:
    return Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
