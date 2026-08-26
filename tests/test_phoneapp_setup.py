"""PhoneApp setup code exchange (QR without embedded finance token)."""

from src.phoneapp_setup import exchange_setup_code, mint_setup_code


def test_setup_code_round_trip():
    code = mint_setup_code(token="ody_test", user="alice", url="https://example.ts.net")
    payload = exchange_setup_code(code)
    assert payload is not None
    assert payload["token"] == "ody_test"
    assert payload["user"] == "alice"
    assert payload["url"] == "https://example.ts.net"


def test_setup_code_single_use():
    code = mint_setup_code(token="ody_test", user="alice", url="https://example.ts.net")
    assert exchange_setup_code(code) is not None
    assert exchange_setup_code(code) is None
