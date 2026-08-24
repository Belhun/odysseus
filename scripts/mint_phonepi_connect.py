#!/usr/bin/env python3
"""Print PhonePi connect hint JSON. Run inside the Odysseus container. No secrets."""
from __future__ import annotations

import json

from src.phonepi import phoneapp_public_url, phonepi_connect_hint, phonepi_setup_deeplink


def main() -> int:
    hint = phonepi_connect_hint()
    print(
        json.dumps(
            {
                "host": hint["host"],
                "port": hint["port"],
                "wsUrl": hint["url"],
                "deeplink": phonepi_setup_deeplink(hint),
                "phoneappUrl": phoneapp_public_url(hint),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
