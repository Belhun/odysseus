#!/usr/bin/env python3
"""Live A–I matrix for Odysseus token + PhoneApp login.

Talks to a running Odysseus (default http://127.0.0.1:7000). Prints pass/fail
with status codes. Never prints full ody_ secrets.

  ODYSSEUS_URL=http://127.0.0.1:7000 \\
  ODYSSEUS_USER=belhun \\
  ODYSSEUS_PASSWORD='...' \\
  ./venv/bin/python scripts/phone_client_connect_matrix.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("ODYSSEUS_URL", "http://127.0.0.1:7000").rstrip("/")
USER = os.environ.get("ODYSSEUS_USER", "belhun")
PASSWORD = os.environ.get("ODYSSEUS_PASSWORD", "")
TIMEOUT = 20

rows: list[dict] = []


def _trim(body: str, n: int = 180) -> str:
    text = " ".join(body.split())
    if "ody_" in text:
        text = text.split("ody_")[0] + "ody_[redacted]"
    return text[:n]


def _request(method: str, path: str, *, json_body=None, headers=None, cookie=None):
    url = BASE + path
    data = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if cookie:
        hdrs["Cookie"] = cookie
    if json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            set_cookie = resp.headers.get("Set-Cookie", "")
            return resp.status, body, set_cookie
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body, exc.headers.get("Set-Cookie", "") if exc.headers else ""


def record(letter: str, name: str, ok: bool, status: int, snippet: str, extra: str = ""):
    rows.append(
        {
            "id": letter,
            "name": name,
            "result": "PASS" if ok else "FAIL",
            "status": status,
            "snippet": snippet,
            "extra": extra,
        }
    )
    mark = "PASS" if ok else "FAIL"
    print(f"{letter}  {mark:4}  HTTP {status}  {name}")
    print(f"    {_trim(snippet)}")
    if extra:
        print(f"    {extra}")


def main() -> int:
    if not PASSWORD:
        print("Set ODYSSEUS_PASSWORD", file=sys.stderr)
        return 2

    status, body, cookie = _request(
        "POST",
        "/api/auth/login",
        json_body={"username": USER, "password": PASSWORD, "remember": True},
    )
    ok = status == 200 and "odysseus_session=" in cookie
    record("A", "Password login POST /api/auth/login", ok, status, body,
           extra="Set-Cookie has odysseus_session" if ok else "missing session cookie")
    session = ""
    for part in cookie.split(","):
        if "odysseus_session=" in part:
            session = part.split(";", 1)[0].strip()
            break
    if not session:
        # urllib may join cookies with comma; also try semicolon-only parse
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("odysseus_session="):
                session = part
                break

    status, body, _ = _request(
        "POST",
        "/api/auth/login",
        json_body={"username": USER, "password": "wrong-password-xxxx", "remember": True},
    )
    record(
        "A2",
        "Wrong password → 401 Invalid credentials",
        status == 401 and "Invalid credentials" in body and "Not authenticated" not in body,
        status,
        body,
    )

    status, body, _ = _request(
        "POST",
        "/api/login",
        json_body={"username": USER, "password": PASSWORD},
    )
    record(
        "B",
        "Wrong path POST /api/login (expected 401 Not authenticated)",
        status == 401 and "Not authenticated" in body,
        status,
        body,
    )

    if not session:
        print("No session; cannot mint tokens", file=sys.stderr)
        return 1

    def mint(name: str, **fields) -> tuple[int, dict]:
        boundary = "----odyboundary"
        parts = []
        for key, value in {"name": name, **fields}.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n"
            )
        parts.append(f"--{boundary}--\r\n")
        data = "".join(parts).encode()
        req = urllib.request.Request(
            BASE + "/api/tokens",
            data=data,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Cookie": session,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"detail": raw}
            return exc.code, parsed

    st, phone = mint("Phone finance", profile="phone_finance")
    phone_token = phone.get("token", "")
    record(
        "C",
        "Mint phone_finance token as admin",
        st == 200 and phone_token.startswith("ody_") and "finance:write" in phone.get("scopes", []),
        st,
        json.dumps({k: v for k, v in phone.items() if k != "token"}),
    )

    st, chat = mint("Codex chat-only", scopes="chat")
    chat_token = chat.get("token", "")
    record(
        "C2",
        "Mint chat-only / companion token",
        st == 200 and chat_token.startswith("ody_") and chat.get("scopes") == ["chat"],
        st,
        json.dumps({k: v for k, v in chat.items() if k != "token"}),
    )

    st, no_finance = mint("Chat plus todos", scopes="chat,todos:read")
    weak_token = no_finance.get("token", "")

    def bearer(token: str, path: str):
        return _request("GET", path, headers={"Authorization": f"Bearer {token}"})

    status, body, _ = bearer(phone_token, "/api/finance/accounts")
    record("D", "Finance GET with phone token", status == 200 and "accounts" in body, status, body)

    status, body, _ = bearer(chat_token, "/api/finance/accounts")
    record("D2", "Finance GET with chat token → 403", status == 403, status, body)

    status, body, _ = bearer(weak_token, "/api/finance/accounts")
    record("E", "Token missing finance scopes → 403", status == 403, status, body)

    # F is a client-side PhoneApp rule; prove server still 401s on empty bearer.
    status, body, _ = _request(
        "GET",
        "/api/finance/accounts",
        headers={"Authorization": "Bearer "},
    )
    record(
        "F",
        "Empty Bearer does not authenticate (no fake password login)",
        status in (401, 403),
        status,
        body,
    )

    status, body, _ = bearer(chat_token, "/api/companion/ping")
    record(
        "I",
        "Companion ping with chat token",
        status == 200 and '"ok"' in body,
        status,
        body,
    )
    status, body, _ = bearer(chat_token, "/api/finance/accounts")
    record(
        "I2",
        "Companion/chat token still 403 on finance",
        status == 403,
        status,
        body,
    )

    failed = [r for r in rows if r["result"] != "PASS"]
    print()
    print(f"{len(rows) - len(failed)}/{len(rows)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
