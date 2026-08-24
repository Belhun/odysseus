"""Regression test for the CORS-preflight auth bypass.

AuthMiddleware is the outermost middleware, so it used to 401 the credential-less
OPTIONS preflight before CORSMiddleware could answer it -- which blocks every
cross-origin browser/WebView client before the real request is ever sent. The
fix lets a genuine preflight through; `is_cors_preflight` is the pure predicate
it uses. Guard it so the bypass can't silently regress.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.middleware import is_cors_preflight


def test_genuine_preflight_is_detected():
    assert is_cors_preflight("OPTIONS", {"access-control-request-method": "POST"}) is True


def test_bare_options_is_not_a_preflight():
    # OPTIONS without Access-Control-Request-Method must NOT bypass auth.
    assert is_cors_preflight("OPTIONS", {}) is False


def test_real_methods_are_never_preflight():
    headers = {"access-control-request-method": "POST"}
    for method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        assert is_cors_preflight(method, headers) is False


def test_localhost_origin_regex_matches_flutter_web_and_not_tsnet():
    import re

    from core.middleware import LOCALHOST_ORIGIN_REGEX

    pat = re.compile(LOCALHOST_ORIGIN_REGEX)
    assert pat.match("http://localhost")
    assert pat.match("http://localhost:12345")
    assert pat.match("http://127.0.0.1:8088")
    assert pat.match("https://127.0.0.1")
    assert not pat.match("https://dell-mini-pc.tailcbcc46.ts.net")
    assert not pat.match("http://100.79.4.36:7000")
    assert not pat.match("https://evil.example")


def test_cors_middleware_allows_localhost_flutter_port():
    from starlette.applications import Starlette
    from starlette.middleware.cors import CORSMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from core.middleware import LOCALHOST_ORIGIN_REGEX

    async def accounts(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/api/finance/accounts", accounts, methods=["GET"])])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost"],
        allow_origin_regex=LOCALHOST_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    origin = "http://localhost:54321"
    response = TestClient(app).options(
        "/api/finance/accounts",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
