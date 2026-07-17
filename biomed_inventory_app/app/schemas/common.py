from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def normalize_text(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalized_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def validate_code(value: str | None, field_name: str = "code") -> str | None:
    value = normalize_text(value)
    if value is None:
        return None
    if not CODE_RE.match(value):
        raise ValueError(f"{field_name} may contain letters, numbers, dot, underscore, or dash")
    return value


def validate_email(value: str | None) -> str | None:
    value = normalize_text(value)
    if value is None:
        return None
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("email must look like an email address")
    return value


def validate_country_code(value: str | None) -> str | None:
    value = normalize_text(value)
    if value is None:
        return None
    value = value.upper()
    if len(value) != 2 or not value.isalpha():
        raise ValueError("country_code must be a two-letter country code")
    return value


class FoundationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def _empty_strings_to_none(cls, value: Any) -> Any:
        return normalize_text(value)


class TimestampFields(FoundationSchema):
    created_at: datetime | None = None
    updated_at: datetime | None = None
