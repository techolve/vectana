from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class Customer(SQLModel, table=True):
    """A client (取引先). Separate from ``Company``, which is our own side of
    the group. Each customer belongs to the group company that deals with it,
    and sales only see their own company's customers."""

    __tablename__ = "customers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True, ondelete="RESTRICT")
    name: str = Field(max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=300)
    payment_terms: str | None = Field(default=None, max_length=200)
    billing_contact: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None)
    sales_owner_id: UUID | None = Field(
        default=None, foreign_key="users.id", index=True, ondelete="SET NULL"
    )
    created_at: datetime = created_at_field()


class CustomerContact(SQLModel, table=True):
    """A person at the customer (担当者)."""

    __tablename__ = "customer_contacts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    customer_id: UUID = Field(foreign_key="customers.id", index=True, ondelete="CASCADE")
    name: str = Field(max_length=100)
    title: str | None = Field(default=None, max_length=200)  # 部署・役職
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool = Field(default=False)
    created_at: datetime = created_at_field()
