from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.matching.service import evaluate_pair
from .config import (
    CATEGORY_ORDER,
    CATEGORY_PRESENTATION,
    PREFERENCE_BANDS,
    PUBLIC_DISCLAIMER,
    SCORE_BANDS,
)


class CompatibilityUnavailable(Exception):
    pass


def _score_band(score: int) -> tuple[str, str]:
    for minimum, key, label in SCORE_BANDS:
        if score >= minimum:
            return key, label
    return "different", "Есть различия"


def _preference_band(score: int) -> str:
    for minimum, key in PREFERENCE_BANDS:
        if score >= minimum:
            return key
    return "different"


def _distance_bucket(distance_km: float | None) -> str | None:
    if distance_km is None:
        return None
    if distance_km <= 10:
        return "nearby"
    if distance_km <= 50:
        return "same_area"
    if distance_km <= 250:
        return "regional"
    return "far"


def _category_cards(scores: dict[str, int]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for key in CATEGORY_ORDER:
        if key not in scores:
            continue
        score = int(scores[key])
        band_key, band_label = _score_band(score)
        presentation = CATEGORY_PRESENTATION[key]
        cards.append(
            {
                "key": key,
                "title": presentation["title"],
                "score": score,
                "level": band_key,
                "level_label": band_label,
            }
        )
    return cards


def _strengths(scores: dict[str, int], limit: int = 3) -> list[str]:
    ranked = sorted(
        (
            (int(score), key)
            for key, score in scores.items()
            if key in CATEGORY_PRESENTATION and int(score) >= 70
        ),
        key=lambda item: (-item[0], CATEGORY_ORDER.index(item[1])),
    )
    return [CATEGORY_PRESENTATION[key]["strength"] for _, key in ranked[:limit]]


def _discussion_points(scores: dict[str, int], limit: int = 2) -> list[str]:
    ranked = sorted(
        (
            (int(score), key)
            for key, score in scores.items()
            if key in CATEGORY_PRESENTATION and int(score) < 70
        ),
        key=lambda item: (item[0], CATEGORY_ORDER.index(item[1])),
    )
    return [CATEGORY_PRESENTATION[key]["discuss"] for _, key in ranked[:limit]]


def _summary_text(score: int) -> str:
    if score >= 85:
        return "По анкете у вас много сильных совпадений."
    if score >= 70:
        return "По анкете у вас заметно больше совпадений, чем различий."
    if score >= 55:
        return "У вас есть хорошие точки совпадения и несколько тем, которые стоит обсудить."
    return "У вас есть совпадения, но по части важных тем ответы заметно различаются."


def build_compatibility_result(
    db: Session,
    *,
    viewer_user_id: int,
    candidate_user_id: int,
    now=None,
) -> dict[str, Any]:
    evaluated = evaluate_pair(
        db,
        viewer_user_id,
        candidate_user_id,
        now=now,
    )
    if not evaluated.get("eligible"):
        raise CompatibilityUnavailable(evaluated.get("reason") or "pair_not_available")

    scores = {
        key: int(value)
        for key, value in (evaluated.get("category_scores") or {}).items()
        if key in CATEGORY_PRESENTATION
    }
    compatibility = int(evaluated.get("compatibility_score") or 0)
    preference_alignment = int(evaluated.get("mutual_preference_score") or 0)
    distance = evaluated.get("distance_km")

    why = _strengths(scores)
    discuss = _discussion_points(scores)

    if not why:
        why = ["Система нашла взаимное соответствие базовым критериям и несколько точек для знакомства."]
    if not discuss:
        discuss = ["Явных зон сильного расхождения по анкете не видно, но важные ожидания всё равно лучше проговорить лично."]

    return {
        "available": True,
        "candidate_user_id": candidate_user_id,
        "algorithm_version": evaluated["algorithm_version"],
        "compatibility_percent": compatibility,
        "summary": _summary_text(compatibility),
        "categories": _category_cards(scores),
        "why_you_match": why,
        "what_to_discuss": discuss,
        "preference_alignment": _preference_band(preference_alignment),
        "distance": {
            "km": distance,
            "bucket": _distance_bucket(distance),
        },
        "disclaimer": PUBLIC_DISCLAIMER,
    }


def safe_ai_explanation_context(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("available"):
        raise CompatibilityUnavailable("compatibility_result_unavailable")

    return {
        "algorithm_version": result.get("algorithm_version"),
        "compatibility_percent": result.get("compatibility_percent"),
        "categories": [
            {
                "key": item["key"],
                "title": item["title"],
                "score": item["score"],
                "level": item["level"],
            }
            for item in result.get("categories", [])
        ],
        "why_you_match": list(result.get("why_you_match", [])),
        "what_to_discuss": list(result.get("what_to_discuss", [])),
        "preference_alignment": result.get("preference_alignment"),
        "distance_bucket": (result.get("distance") or {}).get("bucket"),
        "rules": {
            "may_rephrase_only": True,
            "must_not_change_scores": True,
            "must_not_infer_missing_traits": True,
            "must_not_reveal_raw_answers": True,
            "must_not_reveal_partner_preferences": True,
        },
    }


def public_result_keys() -> set[str]:
    return {
        "available",
        "candidate_user_id",
        "algorithm_version",
        "compatibility_percent",
        "summary",
        "categories",
        "why_you_match",
        "what_to_discuss",
        "preference_alignment",
        "distance",
        "disclaimer",
    }
