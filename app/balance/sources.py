from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Market, MarketingAttribution, Profile, User
from .core import ready_profiles


def source_breakdown(
    db: Session,
    *,
    market_code: str | None = None,
) -> list[dict[str, Any]]:
    ready_ids = {p.user_id for p in ready_profiles(db, market_code=market_code)}

    query = select(User)
    if market_code:
        query = (
            query.join(Profile, Profile.user_id == User.id)
            .join(Market, Market.id == Profile.market_id)
            .where(Market.code == market_code)
        )
    users = list(db.execute(query).scalars())
    attributions = {
        row.user_id: row
        for row in db.execute(select(MarketingAttribution)).scalars()
    }

    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"registrations": 0, "completed_active": 0}
    )
    for user in users:
        attribution = attributions.get(user.id)
        if user.referred_by is not None:
            source = "referral"
        elif attribution is not None and (attribution.utm_source or "").strip():
            source = attribution.utm_source.strip()
        else:
            source = "direct"

        counts[source]["registrations"] += 1
        if user.id in ready_ids:
            counts[source]["completed_active"] += 1

    result = []
    for source, values in counts.items():
        registrations = values["registrations"]
        completed_active = values["completed_active"]
        result.append(
            {
                "source": source,
                "registrations": registrations,
                "completed_active": completed_active,
                "activation_rate": round(
                    completed_active * 100 / max(1, registrations),
                    1,
                ),
            }
        )

    result.sort(key=lambda row: (-row["registrations"], row["source"]))
    return result
