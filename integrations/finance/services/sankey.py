"""Income → category cashflow map from true-spend report helpers.

Do not reimplement cashflow math. Transfers are not spend. Unclassified
outflows already sit in category totals (fail-open); they are annotated,
not linked a second time from Income.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from integrations.finance.services.reports import month_cashflow, spending_by_category, validate_month


def month_sankey(
    db: Session,
    owner: str,
    month: str,
    account_id: Optional[str] = None,
) -> dict[str, Any]:
    month = validate_month(month)
    cash = month_cashflow(db, owner, month, account_id=account_id, include_transfers=False)
    rows = spending_by_category(
        db,
        owner,
        month,
        account_id=account_id,
        include_transfers=False,
        include_zero_limits=False,
    )
    income = int(cash.get("income_cents") or 0)
    nodes: list[dict[str, Any]] = [
        {"id": "income", "label": "Income", "cents": income, "kind": "income"}
    ]
    links: list[dict[str, Any]] = []
    allocated = 0
    for row in rows:
        spent = int(row.get("spent_cents") or 0)
        if spent <= 0:
            continue
        raw_id = row.get("category_id")
        nid = str(raw_id) if raw_id else "uncategorized"
        nodes.append(
            {
                "id": nid,
                "label": row.get("category_name") or "Uncategorized",
                "cents": spent,
                "kind": "category",
                "category_id": raw_id,
                "color": row.get("color"),
            }
        )
        links.append({"source": "income", "target": nid, "cents": spent})
        allocated += spent

    leftover = income - allocated
    if leftover > 0:
        nodes.append(
            {
                "id": "leftover",
                "label": "Leftover",
                "cents": leftover,
                "kind": "leftover",
            }
        )
        links.append({"source": "income", "target": "leftover", "cents": leftover})

    unclassified_count = int(cash.get("unclassified_count") or 0)
    unclassified_out = int(cash.get("unclassified_outflow_cents") or 0)
    incomplete = bool(cash.get("incomplete")) or unclassified_count > 0
    if unclassified_count > 0:
        nodes.append(
            {
                "id": "unclassified",
                "label": "Unclassified",
                "cents": unclassified_out,
                "kind": "unclassified",
            }
        )

    return {
        "month": month,
        "income_cents": income,
        "nodes": nodes,
        "links": links,
        "unclassified_count": unclassified_count,
        "unclassified_outflow_cents": unclassified_out,
        "incomplete": incomplete,
    }
