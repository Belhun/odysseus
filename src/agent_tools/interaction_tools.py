import json
import logging

logger = logging.getLogger(__name__)

class AskUserTool:
    async def execute(self, content, ctx):
        """
        ask_user: the agent poses a multiple-choice question to the user to get a
        decision/clarification. This is a pure UI-control marker — no subprocess,
        no filesystem. It returns an `ask_user` payload that the agent loop turns
        into an `ask_user` SSE event and then ENDS the turn, so the chat waits for
        the user's selection (their choice arrives as the next message).

        Optional ``confirmation`` block mints a session-scoped token for gated
        tool actions (see docs/CONFIRMATION_GATES.md).
        """
        question, options, multi = "", [], False
        confirmation_req = None
        raw = (content or "").strip()
        try:
            parsed = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            parsed = {}

        if isinstance(parsed, dict):
            question = str(parsed.get("question", "")).strip()
            multi = bool(parsed.get("multi") or parsed.get("multiSelect"))
            confirmation_req = parsed.get("confirmation")
            for opt in (parsed.get("options") or []):
                if isinstance(opt, dict):
                    label = str(opt.get("label", "")).strip()
                    descr = str(opt.get("description", "")).strip()
                elif isinstance(opt, str):
                    label, descr = opt.strip(), ""
                else:
                    continue
                if label:
                    options.append({"label": label, "description": descr})
        else:
            question = raw

        if not question or len(options) < 2:
            return "ask_user: invalid", {
                "error": (
                    "ask_user needs a non-empty `question` and at least 2 `options` "
                    "(each an object with a `label`, optional `description`)."
                ),
                "exit_code": 1,
            }

        options = options[:6]  # keep the choice list sane
        desc = f"ask_user: {question[:80]}"
        labels = ", ".join(o["label"] for o in options)
        ask_payload = {"question": question, "options": options, "multi": multi}

        if isinstance(confirmation_req, dict) and confirmation_req.get("domain"):
            from src.confirmation_gates import mint_confirmation

            session_id = (ctx or {}).get("session_id") or ""
            owner = (ctx or {}).get("owner") or ""
            token, mint_err = mint_confirmation(
                session_id=session_id,
                owner=owner,
                domain=str(confirmation_req.get("domain", "")),
                tool_name=str(confirmation_req.get("tool") or confirmation_req.get("tool_name") or ""),
                action=str(confirmation_req.get("action", "")),
                payload=dict(confirmation_req.get("payload") or {}),
                approve_labels=confirmation_req.get("approve_labels"),
                ttl_seconds=confirmation_req.get("ttl_seconds"),
            )
            if mint_err:
                return "ask_user: invalid confirmation", {
                    "error": mint_err,
                    "exit_code": 1,
                }
            ask_payload["confirmation_token"] = token
            ask_payload["confirmation"] = {
                "domain": confirmation_req.get("domain"),
                "tool": confirmation_req.get("tool") or confirmation_req.get("tool_name"),
                "action": confirmation_req.get("action"),
            }

        output = f"Asked the user: {question}\nOptions: {labels}\nAwaiting their selection."
        if ask_payload.get("confirmation_token"):
            batch_note = ""
            if isinstance(confirmation_req, dict):
                items = confirmation_req.get("items")
                max_uses = confirmation_req.get("max_uses")
                if isinstance(items, list) and len(items) > 1:
                    batch_note = (
                        f" Batch approval covers {len(items)} items; reuse the same "
                        f"confirmation_token for each gated call, or use a single "
                        f"create_categories call with the full categories array."
                    )
                elif max_uses and int(max_uses) > 1:
                    batch_note = (
                        f" This token allows {int(max_uses)} gated calls; reuse the same "
                        f"confirmation_token until all approved work is done."
                    )
            output += (
                f"\nConfirmation token minted. After the user approves, pass "
                f'confirmation_token="{ask_payload["confirmation_token"]}" in each gated tool call.'
                f"{batch_note}"
            )

        result = {
            "ask_user": ask_payload,
            "output": output,
            "exit_code": 0,
        }
        logger.info("Tool executed: %s (%d options, multi=%s)", desc, len(options), multi)
        return desc, result

class UpdatePlanTool:
    async def execute(self, content, ctx):
        """
        update_plan: the agent writes back to the active plan — tick an item done
        or revise steps (e.g. when the user asks to change something). Pure UI
        marker: returns a `plan_update` payload the agent loop turns into a
        `plan_update` SSE event; the frontend replaces the stored plan and refreshes
        the docked plan window. Does NOT end the turn.
        """
        raw = (content or "").strip()
        plan = ""
        try:
            parsed = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            parsed = {}

        if isinstance(parsed, dict) and parsed.get("plan"):
            plan = str(parsed.get("plan", "")).strip()
        else:
            plan = raw

        if not plan:
            return "update_plan: invalid", {
                "error": "update_plan needs a non-empty `plan` (the full updated checklist as markdown).",
                "exit_code": 1,
            }

        plan = plan[:8192]
        done = plan.count("- [x]") + plan.count("- [X]")
        total = done + plan.count("- [ ]")
        desc = f"update_plan: {done}/{total} done" if total else "update_plan"
        result = {
            "plan_update": {"plan": plan},
            "output": f"Plan updated ({done}/{total} steps complete)." if total else "Plan updated.",
            "exit_code": 0,
        }
        logger.info("Tool executed: %s", desc)
        return desc, result