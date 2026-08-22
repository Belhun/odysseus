"""Static contract for Settings → Phone app token (not PhonePi)."""

from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_INDEX = (_REPO / "static" / "index.html").read_text(encoding="utf-8")
_SETTINGS = (_REPO / "static" / "js" / "settings.js").read_text(encoding="utf-8")
_APP = (_REPO / "static" / "app.js").read_text(encoding="utf-8")
_ADMIN = (_REPO / "static" / "js" / "admin.js").read_text(encoding="utf-8")


def test_settings_has_phone_app_token_tab_not_phonepi():
    assert 'data-settings-tab="phone-app-token"' in _INDEX
    assert 'data-settings-panel="phone-app-token"' in _INDEX
    assert "Create Phone finance token" in _INDEX
    assert "phone_finance" in _SETTINGS
    assert "PhonePi" in _INDEX
    # Settings → Phone / PhonePi is MCP, not this mint UI.
    assert "not Settings → Phone / PhonePi" in _INDEX


def test_create_phone_finance_posts_profile():
    assert "fd.append('profile', 'phone_finance')" in _SETTINGS
    assert "id=\"phone-token-create-btn\"" in _INDEX
    assert "id=\"phone-token-value\"" in _INDEX


def test_user_bar_key_opens_phone_token_tab():
    assert 'id="user-bar-phone-token"' in _INDEX
    assert "adminModule.open('phone-app-token')" in _APP


def test_admin_token_form_exposes_finance_scopes():
    assert "id=\"adm-tokenName\"" in _INDEX
    assert "id=\"adm-tokenAddBtn\"" in _INDEX
    assert "finance:read" in _ADMIN
    assert "finance:write" in _ADMIN
