"""Encrypt repository access tokens at rest with a key derived from SECRET_KEY.
Changing SECRET_KEY makes stored tokens unreadable: re-enter them."""

import base64
import hashlib
import secrets as _secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"vectana-repo-token:" + settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt(blob: str) -> str | None:
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return None


def new_webhook_secret() -> str:
    return _secrets.token_urlsafe(32)
