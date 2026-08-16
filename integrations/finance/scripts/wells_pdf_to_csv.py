"""CLI: Wells Fargo statement PDFs → Odysseus-ready CSV.

Run from the repo root:

    python -m integrations.finance.scripts.wells_pdf_to_csv ^
        "C:\\Users\\You\\Downloads\\wells-pdfs" ^
        -o "C:\\Users\\You\\Downloads\\wells-from-statements.csv"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from integrations.finance.services.wells_statement_pdf import (
    WellsStatementError,
    convert_wells_statements,
    expand_pdf_inputs,
    format_convert_report,
    result_to_csv,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Wells Fargo statement PDFs into one signed CSV with a verified opening posted."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="PDF files and/or a folder of monthly statements",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="CSV path to write",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional text report path (defaults to <output>.report.txt)",
    )
    args = parser.parse_args(argv)

    try:
        pdfs = expand_pdf_inputs(args.paths)
        result = convert_wells_statements(pdfs)
    except WellsStatementError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    csv_text = result_to_csv(result)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(csv_text, encoding="utf-8")
    report = format_convert_report(result)
    report_path = Path(args.report) if args.report else out.with_suffix(".report.txt")
    report_path.write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    print(f"Wrote {out}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
