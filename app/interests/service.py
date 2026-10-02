from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.db.models import (
    Interest,
    Match,
    MatchScoreComponent,
    Notification,
    ProductEvent,
)
from app.matching.service import evaluate_pair
from app.prelaunch.policy import candidate_output_enabled


SKIP_COOLDOWN = timedelta(days=30)


class InterestError(Exception):
    pass


class InterestUnavailable(InterestError):
    pass


class InterestActionsDisabled(InterestError):
    pass


class PairAlreadyMatched(InterestError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def interest_actions_enabled(db: Session) -> bool:
    return candidate_output_enabled(db)


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    if a == b:
        raise InterestUnavailable("same_user")
    return (a, b) if a < b else (b, a)


def _advisory_key(a: int, b: int) -> int:
    low, high = _canonical_pair(a, b)
    raw = hashlib.sha256(f"matchlab-interest:{low}:{high}".encode()).digest()[:8]
    return int.from_bytes(raw, "big") & 0x7FFFFFFFFFFFFFFF


def _lock_pair(db: Session, a: int, b: int) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": _advisory_key(a, b)},
    )


def get_match(db: Session, user_a: int, user_b: int) -> Match | None:
    low, high = _canonical_pair(user_a, user_b)
    return db.execute(
        select(Match).where(Match.user1 == low, Match.user2 == high)
    ).scalar_one_or_none()


def get_decision(db: Session, from_user: int, to_user: int) -> Interest | None:
    return db.get(Interest, (from_user, to_user))


def _persist_match_components(
    db: Session,
    *,
    match: Match,
    evaluated: dict[str, Any],
) -> None:
    for key, score in (evaluated.get("category_scores") or {}).items():
        db.add(
            MatchScoreComponent(
                match_id=match.id,
                component_key=key,
                score=score,
                explanation_data={"kind": "questionnaire_category"},
            )
        )

    internal = {
        "mutual_preference_score": evaluated.get("mutual_preference_score"),
        "activity_score": evaluated.get("activity_score"),
        "readiness_score": evaluated.get("readiness_score"),
    }
    for key, score in internal.items():
        if score is None:
            continue
        db.add(
            MatchScoreComponent(
                match_id=match.id,
                component_key=key,
                score=score,
                explanation_data={"kind": "internal_ranking_component"},
            )
        )


def _create_match(
    db: Session,
    *,
    user_a: int,
    user_b: int,
    evaluated: dict[str, Any],
    now: datetime,
) -> Match:
    low, high = _canonical_pair(user_a, user_b)
    existing = get_match(db, low, high)
    if existing is not None:
        return existing

    match = Match(
        user1=low,
        user2=high,
        compatibility_score=int(evaluated["compatibility_score"]),
        mutual_fit_score=int(evaluated["final_mutual_fit_score"]),
        algorithm_version=str(evaluated["algorithm_version"]),
        created_at=now,
    )
    db.add(match)
    db.flush()
    _persist_match_components(db, match=match, evaluated=evaluated)

    low_notification = Notification(
        user_id=low,
        kind="MATCH",
        text="У вас взаимный интерес — можно начать общение.",
        created_at=now,
    )
    high_notification = Notification(
        user_id=high,
        kind="MATCH",
        text="У вас взаимный интерес — можно начать общение.",
        created_at=now,
    )
    db.add_all(
        [
            low_notification,
            high_notification,
            ProductEvent(
                user_id=None,
                event_type="MUTUAL_MATCH_CREATED",
                metadata_json={
                    "match_id": match.id,
                    "algorithm_version": match.algorithm_version,
                },
                created_at=now,
            ),
        ]
    )
    db.flush()

    from app.push.service import enqueue_notification

    enqueue_notification(db, notification_id=low_notification.id, now=now)
    enqueue_notification(db, notification_id=high_notification.id, now=now)
    return match


def record_decision(
    db: Session,
    *,
    from_user: int,
    to_user: int,
    state: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    state = (state or "").upper()
    if state not in {"INTERESTED", "SKIPPED"}:
        raise InterestError("Unsupported candidate decision")
    if from_user == to_user:
        raise InterestUnavailable("same_user")
    if not interest_actions_enabled(db):
        raise InterestActionsDisabled("Candidate actions are disabled in pre-launch mode")

    _lock_pair(db, from_user, to_user)

    existing_match = get_match(db, from_user, to_user)
    if existing_match is not None:
        if state == "SKIPPED":
            raise PairAlreadyMatched("Pair already has a mutual match")
        return {
            "state": "INTERESTED",
            "changed": False,
            "mutual_match": True,
            "match_id": existing_match.id,
            "candidate_user_id": to_user,
        }

    evaluated = evaluate_pair(db, from_user, to_user, now=now)
    if not evaluated.get("eligible"):
        raise InterestUnavailable(evaluated.get("reason") or "pair_not_available")

    row = get_decision(db, from_user, to_user)
    active_same_skip = (
        row is not None
        and row.state == "SKIPPED"
        and row.snooze_until is not None
        and row.snooze_until > now
    )
    same = (
        row is not None
        and (
            (state == "INTERESTED" and row.state == "INTERESTED")
            or (state == "SKIPPED" and active_same_skip)
        )
    )

    if row is None:
        row = Interest(
            from_user=from_user,
            to_user=to_user,
            state=state,
            source_algorithm_version=str(evaluated["algorithm_version"]),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    elif not same:
        row.state = state
        row.source_algorithm_version = str(evaluated["algorithm_version"])
        row.updated_at = now

    if state == "SKIPPED":
        if not same:
            row.snooze_until = now + SKIP_COOLDOWN
    else:
        row.snooze_until = None

    if not same:
        db.add(
            ProductEvent(
                user_id=from_user,
                event_type="INTEREST_EXPRESSED" if state == "INTERESTED" else "CANDIDATE_SKIPPED",
                metadata_json={
                    "candidate_user_id": to_user,
                    "algorithm_version": str(evaluated["algorithm_version"]),
                },
                created_at=now,
            )
        )
    db.flush()

    if state != "INTERESTED":
        return {
            "state": state,
            "changed": not same,
            "mutual_match": False,
            "match_id": None,
            "candidate_user_id": to_user,
            "snooze_until": row.snooze_until,
        }

    reverse = get_decision(db, to_user, from_user)
    if reverse is None or reverse.state != "INTERESTED":
        return {
            "state": state,
            "changed": not same,
            "mutual_match": False,
            "match_id": None,
            "candidate_user_id": to_user,
        }

    # Re-evaluate while holding the pair advisory lock. A profile/status/block may
    # have changed since the first interest was recorded.
    evaluated = evaluate_pair(db, from_user, to_user, now=now)
    if not evaluated.get("eligible"):
        raise InterestUnavailable(evaluated.get("reason") or "pair_not_available")

    match = _create_match(
        db,
        user_a=from_user,
        user_b=to_user,
        evaluated=evaluated,
        now=now,
    )
    return {
        "state": state,
        "changed": not same,
        "mutual_match": True,
        "match_id": match.id,
        "candidate_user_id": to_user,
    }


def express_interest(
    db: Session,
    *,
    from_user: int,
    to_user: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    return record_decision(
        db,
        from_user=from_user,
        to_user=to_user,
        state="INTERESTED",
        now=now,
    )


def skip_candidate(
    db: Session,
    *,
    from_user: int,
    to_user: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    return record_decision(
        db,
        from_user=from_user,
        to_user=to_user,
        state="SKIPPED",
        now=now,
    )
