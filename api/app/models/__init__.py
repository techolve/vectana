"""Import every model so its table registers on SQLModel.metadata."""

from app.models.customer import Customer, CustomerContact
from app.models.eol import AppSettings, EolDelivery, EolFinding, Runtime
from app.models.estimate import Estimate, EstimateLine
from app.models.invitation import Invitation
from app.models.notification import NotificationDelivery, NotificationPref
from app.models.organization import Company, Department, UserDepartment
from app.models.package import Package, VulnMatch, VulnMatchEvent
from app.models.project import Project, ProjectMember, ProjectWebhook
from app.models.report import ReportDelivery
from app.models.token import ApiToken
from app.models.user import User

__all__ = [
    "ApiToken",
    "AppSettings",
    "EolDelivery",
    "EolFinding",
    "Runtime",
    "Company",
    "Customer",
    "CustomerContact",
    "Estimate",
    "EstimateLine",
    "Department",
    "Invitation",
    "NotificationDelivery",
    "NotificationPref",
    "Package",
    "Project",
    "ProjectMember",
    "ProjectWebhook",
    "ReportDelivery",
    "User",
    "UserDepartment",
    "VulnMatch",
    "VulnMatchEvent",
]
