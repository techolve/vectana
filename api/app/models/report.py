from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class ReportDelivery(SQLModel, table=True):
    """One periodic organization report sent to one user for one period
    (ISO week, e.g. ``2026-W45``). Keeps the weekly report to once a week."""

    __tablename__ = "report_deliveries"
    __table_args__ = (UniqueConstraint("user_id", "period"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    period: str = Field(max_length=20)
    sent_at: datetime = created_at_field()
