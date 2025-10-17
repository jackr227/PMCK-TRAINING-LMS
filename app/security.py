from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.hash import bcrypt
from starlette.requests import Request

CSRF_NAMESPACE = "pmck-training-csrf"
CSRF_TOKEN_KEY = "csrf_token"
SESSION_USER_KEY = "user_id"
SESSION_BRAND_KEY = "brand_slug"


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.verify(password, password_hash)
    except ValueError:
        return False


def _serializer(request: Request) -> URLSafeTimedSerializer:
    secret = request.app.state.csrf_secret
    return URLSafeTimedSerializer(secret_key=secret, salt=CSRF_NAMESPACE)


def generate_csrf_token(request: Request) -> str:
    token = _serializer(request).dumps({"ts": datetime.utcnow().isoformat()})
    request.session[CSRF_TOKEN_KEY] = token
    return token


def validate_csrf(request: Request, token: str, max_age: int = 3600) -> None:
    stored = request.session.get(CSRF_TOKEN_KEY)
    if not stored or stored != token:
        raise ValueError("csrf-mismatch")
    try:
        _serializer(request).loads(token, max_age=max_age)
    except BadSignature as exc:  # pragma: no cover - defensive
        raise ValueError("csrf-expired") from exc


__all__ = [
    "hash_password",
    "verify_password",
    "generate_csrf_token",
    "validate_csrf",
    "SESSION_USER_KEY",
    "SESSION_BRAND_KEY",
]
