"""Extract cited chat-review Write payloads from agent transcripts."""
from __future__ import annotations

import json
import pathlib

BASE = pathlib.Path(
    r"C:\Users\User\.cursor\projects\f-Codeing-Project-odysseus-sysforge\agent-transcripts"
)
OUT = pathlib.Path(__file__).resolve().parent / "_extracted"
OUT.mkdir(parents=True, exist_ok=True)

WANTED = ("21e672a5", "920df407", "21972123", "f4de4b62", "8eceb374")


def main() -> int:
    found: dict[str, tuple[str, str, str]] = {}
    for path in BASE.rglob("*.jsonl"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "chat-reviews" not in text:
            continue
        for line in text.splitlines():
            if "chat-reviews" not in line or "Write" not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            for part in obj.get("message", {}).get("content", []):
                if part.get("type") != "tool_use" or part.get("name") != "Write":
                    continue
                inp = part.get("input") or {}
                dest = (inp.get("path") or "").replace("\\", "/")
                contents = inp.get("contents")
                if not contents or "chat-reviews" not in dest:
                    continue
                for kid in WANTED:
                    if kid in dest and kid not in found:
                        found[kid] = (dest, contents, path.name)

    for kid, (dest, contents, src) in found.items():
        name = pathlib.Path(dest).name
        (OUT / name).write_text(contents, encoding="utf-8")
        print(f"wrote {name} from {src} ({len(contents)} chars)")

    for kid in WANTED:
        if kid not in found:
            print(f"MISSING {kid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
