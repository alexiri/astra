from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.core import signing


def make_signed_token(payload: Mapping[str, Any]) -> str:
    return signing.dumps(dict(payload), salt=settings.SECRET_KEY)


def read_signed_token(token: str) -> dict[str, Any]:
    return signing.loads(
        token,
        salt=settings.SECRET_KEY,
        max_age=settings.EMAIL_VALIDATION_TOKEN_TTL_SECONDS,
    )
