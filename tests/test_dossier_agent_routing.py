"""U5: dossier tools in security blocklist + domain map."""
from src.tool_security import NON_ADMIN_BLOCKED_TOOLS
from src.agent_loop import _DOMAIN_TOOL_MAP, _DOMAIN_RULES
from src.tool_index import BUILTIN_TOOL_DESCRIPTIONS, ASSISTANT_ALWAYS_AVAILABLE


def test_dossier_tools_blocked_for_non_admin():
    for name in ("manage_dossier", "manage_archive", "search_dossier"):
        assert name in NON_ADMIN_BLOCKED_TOOLS


def test_dossier_domain_map_and_rules():
    assert _DOMAIN_TOOL_MAP["dossier"] == {
        "manage_dossier",
        "manage_archive",
        "search_dossier",
    }
    assert "dossier" in _DOMAIN_RULES
    assert "manage_memory" in _DOMAIN_RULES["dossier"]
    assert "untrusted" in _DOMAIN_RULES["dossier"].lower()


def test_dossier_tool_index_descriptions():
    for name in ("manage_dossier", "manage_archive", "search_dossier"):
        assert name in BUILTIN_TOOL_DESCRIPTIONS
        assert name in ASSISTANT_ALWAYS_AVAILABLE
    assert "untrusted" in BUILTIN_TOOL_DESCRIPTIONS["search_dossier"].lower()
