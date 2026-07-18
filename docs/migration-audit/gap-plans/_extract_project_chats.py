"""Extract project/WO chat reviews from agent transcripts."""
from __future__ import annotations

import json
import pathlib

BASE = pathlib.Path(
    r"C:\Users\User\.cursor\projects\f-Codeing-Project-odysseus-sysforge"
    r"\agent-transcripts"
)
OUT = pathlib.Path(__file__).resolve().parent / "_extracted"
OUT.mkdir(parents=True, exist_ok=True)
WANT = ("c6ee4808", "5d77cdc9", "38ff5cc4", "039b6dc2")


def iter_writes(jsonl_path: pathlib.Path):
    for line in jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "Write" not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        for part in obj.get("message", {}).get("content", []):
            if part.get("type") != "tool_use" or part.get("name") != "Write":
                continue
            inp = part.get("input") or {}
            path = inp.get("path") or ""
            contents = inp.get("contents")
            if path and contents is not None:
                yield path, contents


def main() -> int:
    found = {}
    for p in BASE.rglob("*.jsonl"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if not any(w in text for w in WANT):
            continue
        for path, contents in iter_writes(p):
            norm = path.replace("\\", "/")
            if "chat-reviews" not in norm:
                continue
            for w in WANT:
                if w in norm:
                    name = pathlib.Path(path).name
                    (OUT / name).write_text(contents, encoding="utf-8")
                    found[w] = name
                    print("wrote", name, "from", p.name)
    print("FOUND", found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
