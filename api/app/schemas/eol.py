from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RuntimeBody(BaseModel):
    product: str
    version: str

    @field_validator("product", "version")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class RuntimeOut(BaseModel):
    id: UUID
    product: str
    version: str
    source: str


class EolFindingOut(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str
    source: str  # package | runtime
    product: str
    product_label: str
    version: str
    cycle: str | None
    eol_date: date | None
    latest: str | None
    status: str
    checked_at: datetime | None


class ProductOut(BaseModel):
    name: str
    label: str
    category: str | None = None


class SystemSettings(BaseModel):
    eol_warning_days: int = Field(ge=1, le=730)
    sla_critical_days: int = 7
    sla_high_days: int = 30
    sla_medium_days: int = 90
    sla_low_days: int = 180
    sla_unknown_days: int = 90
    report_enabled: bool = True
    report_weekday: int = 0  # 0 = Monday
