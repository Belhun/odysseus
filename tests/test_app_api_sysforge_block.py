"""app_api must not be used for SysForge Business."""

import json

import pytest

from src.tools.system import do_app_api


@pytest.mark.asyncio
async def test_app_api_sysforge_get_blocked():
    result = await do_app_api(
        json.dumps({"action": "call", "method": "GET", "path": "/api/sysforge/clients"}),
        owner="alice",
    )
    assert result["exit_code"] == 1
    assert "manage_sysforge" in result["error"]


@pytest.mark.asyncio
async def test_app_api_sysforge_post_blocked():
    result = await do_app_api(
        json.dumps({
            "action": "call",
            "method": "POST",
            "path": "/api/sysforge/clients",
            "body": {"first_name": "X"},
        }),
        owner="alice",
    )
    assert result["exit_code"] == 1
    assert "manage_sysforge" in result["error"]
