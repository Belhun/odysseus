from core.models import ChatMessage

from src.tool_pins import (
    finance_domain_matches,
    merge_pinned_tools,
    normalize_pinned_tools,
    pinned_tools_from_history,
)


def test_finance_domain_activation_and_fresh_weather():
    assert finance_domain_matches("Show my Wells Fargo transactions")
    assert not finance_domain_matches("What is the weather?")
    assert not finance_domain_matches("Dice & Drip is entertainment")


def test_persisted_pin_keeps_merchant_and_low_signal_followups():
    history = [
        ChatMessage(
            role="system",
            content="[Conversation summary]",
            metadata={"pinned_tools": ["manage_finance"]},
        ),
        ChatMessage(role="user", content="Dice & Drip is entertainment"),
        ChatMessage(role="user", content="GOOGLE VOICE was a one-time thing"),
        ChatMessage(role="user", content="set the class's"),
        ChatMessage(role="user", content="How about now?"),
    ]
    assert pinned_tools_from_history(history) == {"manage_finance"}


def test_manage_finance_tool_event_activates_pin():
    history = [
        {
            "role": "assistant",
            "content": "done",
            "metadata": {
                "tool_events": [
                    {"tool": "manage_finance", "action": "list_transactions"}
                ]
            },
        }
    ]
    assert pinned_tools_from_history(history) == {"manage_finance"}


def test_pin_allowlist_rejects_forged_tools():
    metadata = merge_pinned_tools(
        {"pinned_tools": ["bash", "web_search"]},
        {"manage_finance", "manage_tokens"},
    )
    assert metadata["pinned_tools"] == ["manage_finance"]
    assert normalize_pinned_tools(metadata["pinned_tools"]) == {"manage_finance"}


def test_separate_fresh_chat_does_not_share_pin():
    finance_chat = [
        ChatMessage(role="user", content="Show my bank transactions"),
    ]
    weather_chat = [
        ChatMessage(role="user", content="What is the weather?"),
    ]
    assert pinned_tools_from_history(finance_chat) == {"manage_finance"}
    assert pinned_tools_from_history(weather_chat) == set()
