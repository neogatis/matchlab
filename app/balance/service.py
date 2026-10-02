from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .core import overview
from .matrix import deficit_insights, supply_demand_matrix
from .sources import source_breakdown


def build_balance_report(
    db: Session,
    *,
    market_code: str | None = None,
) -> dict[str, Any]:
    matrix = supply_demand_matrix(db, market_code=market_code)
    return {
        "overview": overview(db, market_code=market_code),
        "supply_demand": matrix,
        "total_demand_gap": sum(row["gap"] for row in matrix),
        "insights": deficit_insights(db, market_code=market_code),
        "sources": source_breakdown(db, market_code=market_code),
    }
