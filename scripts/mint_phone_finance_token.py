#!/usr/bin/env python3
"""Mint a phone_finance ody_ token. Run inside the Odysseus container."""
from __future__ import annotations

import json
import os
import secrets
import sys
import uuid

import bcrypt

from core.database import get_db_session, ApiToken

SCOPES = "finance:read,finance:write"


def _owner() -> str:
    return (os.environ.get("ODYSSEUS_OWNER") or os.environ.get("ODYSSEUS_USER") or "admin").strip()


def main() -> int:
    name = "PhoneApp"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        name = sys.argv[1].strip()[:100]
    owner = _owner()
    raw = "ody_" + secrets.token_urlsafe(32)
    token_hash = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    token_id = str(uuid.uuid4())[:8]
    with get_db_session() as db:
        db.add(
            ApiToken(
                id=token_id,
                owner=owner,
                name=name,
                token_hash=token_hash,
                token_prefix=raw[:8],
                scopes=SCOPES,
                is_active=True,
            )
        )
    print(json.dumps({"id": token_id, "owner": owner, "name": name, "scopes": SCOPES.split(","), "token": raw}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
