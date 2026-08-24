#!/usr/bin/env python3
"""Mint a phone_finance ody_ token as belhun. Run inside the Odysseus container.

  docker compose exec -T odysseus python /app/scripts/mint_phone_finance_token.py
"""
from __future__ import annotations

import json
import secrets
import sys
import uuid

import bcrypt

from core.database import get_db_session, ApiToken


OWNER = "belhun"
SCOPES = "finance:read,finance:write"


def main() -> int:
    name = "Pixel PhoneApp"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        name = sys.argv[1].strip()[:100]
    raw = "ody_" + secrets.token_urlsafe(32)
    token_hash = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    token_id = str(uuid.uuid4())[:8]
    with get_db_session() as db:
        db.add(
            ApiToken(
                id=token_id,
                owner=OWNER,
                name=name,
                token_hash=token_hash,
                token_prefix=raw[:8],
                scopes=SCOPES,
                is_active=True,
            )
        )
    print(
        json.dumps(
            {
                "id": token_id,
                "owner": OWNER,
                "name": name,
                "scopes": SCOPES.split(","),
                "token": raw,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
