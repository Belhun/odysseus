"""Client query parsing, phone normalize, FTS sanitize, display name, validation."""

from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.IGNORECASE)

FIRST_LAST_MAX = 100
COMPANY_NICKNAME_MAX = 200


class ClientValidationError(ValueError):
    """Invalid client payload (maps to HTTP 400)."""


def normalize_phone(raw: str | None) -> str:
    """Digits-only phone (desktop ClientDocumentMapper.NormalizePhone)."""
    if not raw:
        return ""
    return "".join(ch for ch in raw if ch.isdigit())


def parse_client_query(query: str | None) -> tuple[str | None, str | None, str | None]:
    """Return (phone, email, name). Email by '@'; phone by 7+ digits; else name."""
    if query is None or not str(query).strip():
        return (None, None, None)
    trimmed = str(query).strip()
    if "@" in trimmed:
        return (None, trimmed, None)
    digits = normalize_phone(trimmed)
    if len(digits) >= 7:
        return (trimmed, None, None)
    return (None, None, trimmed)


def has_contact_info(query: str | None) -> bool:
    phone, email, _ = parse_client_query(query)
    return phone is not None or email is not None


def display_name(row: dict[str, Any] | Any) -> str:
    """Nickname → First+Last → First → Last → Company → Unknown."""
    get = row.get if isinstance(row, dict) else lambda k, d=None: getattr(row, k, d)

    def _s(*keys: str) -> str:
        for key in keys:
            val = get(key) if callable(get) else None
            if isinstance(row, dict):
                val = row.get(key)
            elif not isinstance(row, dict):
                val = getattr(row, key, None)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""

    nick = _s("nickname", "Nickname")
    if nick:
        return nick
    first = _s("first_name", "FirstName")
    last = _s("last_name", "LastName")
    if first and last:
        return f"{first} {last}"
    if first:
        return first
    if last:
        return last
    company = _s("company", "Company")
    if company:
        return company
    return "Unknown"


def sanitize_fts_query(query: str) -> str | None:
    """Conservative FTS5 MATCH string (host session_search pattern)."""
    parts: list[str] = []
    for match in re.finditer(r'"([^"]+)"|[\w][\w._-]*', query, flags=re.UNICODE):
        phrase = match.group(1)
        if phrase is not None:
            phrase = phrase.strip()
            if phrase:
                parts.append('"' + phrase.replace('"', '""') + '"')
            continue
        token = match.group(0).strip("._-")
        if not token:
            continue
        if any(ch in token for ch in "._-"):
            parts.append('"' + token.replace('"', '""') + '"')
        else:
            parts.append(token)
    if not parts:
        return None
    return " ".join(parts)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_client(payload: dict[str, Any]) -> None:
    """Desktop ClientValidationHelpers parity."""
    first = payload.get("first_name")
    last = payload.get("last_name")
    company = payload.get("company")
    phone = payload.get("phone_number")
    email = payload.get("email")
    nickname = payload.get("nickname")

    has_name = not _blank(first) or not _blank(last)
    has_company = not _blank(company)
    has_phone = not _blank(phone)
    has_email = not _blank(email)

    if not has_name and not has_company and not has_phone and not has_email:
        raise ClientValidationError(
            "Client must have at least one of: name, company, phone number, or email."
        )

    if not _blank(email) and not EMAIL_RE.match(str(email).strip()):
        raise ClientValidationError("Email address format is invalid.")

    if not _blank(first) and len(str(first)) > FIRST_LAST_MAX:
        raise ClientValidationError(
            f"First name must be at most {FIRST_LAST_MAX} characters."
        )
    if not _blank(last) and len(str(last)) > FIRST_LAST_MAX:
        raise ClientValidationError(
            f"Last name must be at most {FIRST_LAST_MAX} characters."
        )
    if not _blank(company) and len(str(company)) > COMPANY_NICKNAME_MAX:
        raise ClientValidationError(
            f"Company must be at most {COMPANY_NICKNAME_MAX} characters."
        )
    if not _blank(nickname) and len(str(nickname)) > COMPANY_NICKNAME_MAX:
        raise ClientValidationError(
            f"Nickname must be at most {COMPANY_NICKNAME_MAX} characters."
        )
