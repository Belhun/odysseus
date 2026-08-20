"""Drop named packages from a pip requirements file.

Used at image build when INSTALL_OPTIONAL=true so a host can keep PDF/Office
extras without installing local-AI optional packages such as faster-whisper.

Usage:
  python filter_optional_requirements.py requirements-optional.txt "$OPTIONAL_EXCLUDE"
"""

from __future__ import annotations

import re
import sys


def filter_requirement_lines(text: str, exclude: str) -> str:
    skip = {name.strip() for name in exclude.split(",") if name.strip()}
    kept: list[str] = []
    for raw in text.splitlines():
        name = re.sub(r"[ \t]*#.*$", "", raw).strip()
        if name not in skip:
            kept.append(raw)
    return "\n".join(kept) + ("\n" if kept else "")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: filter_optional_requirements.py <requirements-file> [comma-separated-names]", file=sys.stderr)
        return 2
    path = argv[1]
    exclude = argv[2] if len(argv) > 2 else ""
    with open(path, encoding="utf-8") as handle:
        sys.stdout.write(filter_requirement_lines(handle.read(), exclude))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
