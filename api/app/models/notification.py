from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class NotificationPref(SQLModel, table=True):
    """Per-user email preferences. A missing row means the defaults."""

    __tablename__ = "notification_prefs"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True, ondelete="CASCADE")
    email_enabled: bool = Field(default=True)
    min_severity: str = Field(default="LOW", max_length=20)


class NotificationDelivery(SQLModel, table=True):
    """One match delivered to one target. Missing rows are retried next run."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("match_id", "channel", "target"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    match_id: UUID = Field(foreign_key="vuln_matches.id", index=True, ondelete="CASCADE")
    channel: str = Field(max_length=20)  # email | discord | slack
    target: str = Field(max_length=1000)  # email address or webhook id
    sent_at: datetime = created_at_field()
