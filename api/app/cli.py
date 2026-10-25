"""Admin CLI.

    python -m app.cli create-admin --email you@example.com [--name 名前] [--company 会社名]

Creates (or promotes) a group administrator. The password is read from the
VECTANA_ADMIN_PASSWORD env var or prompted for interactively.
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlmodel import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.organization import Company, CompanyType
from app.models.user import User, UserRole


async def create_admin(email: str, name: str | None, company_name: str | None) -> None:
    email = email.lower()
    async with AsyncSessionLocal() as session:
        company_id = None
        if company_name:
            company = (
                await session.exec(select(Company).where(Company.name == company_name))
            ).first()
            if company is None:
                company = Company(name=company_name, type=CompanyType.parent)
                session.add(company)
                await session.flush()
            company_id = company.id

        user = (await session.exec(select(User).where(User.email == email))).first()
        if user is not None:
            user.role = UserRole.group_admin
            user.is_active = True
            session.add(user)
            await session.commit()
            print(f"Promoted {email} to group admin")
            return

        password = os.environ.get("VECTANA_ADMIN_PASSWORD") or getpass.getpass("Password: ")
        if len(password) < 8:
            sys.exit("Password must be at least 8 characters")
        session.add(
            User(
                email=email,
                hashed_password=hash_password(password),
                display_name=name,
                role=UserRole.group_admin,
                company_id=company_id,
            )
        )
        await session.commit()
        print(f"Created group admin {email}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--email", required=True)
    p.add_argument("--name")
    p.add_argument("--company", help="parent company to create/attach")
    args = parser.parse_args()
    if args.command == "create-admin":
        asyncio.run(create_admin(args.email, args.name, args.company))


if __name__ == "__main__":
    main()
