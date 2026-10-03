from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Profile,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    QuestionnaireVersion,
    User,
)
from app.profile.service import profile_completion_state
from .policy import candidate_output_enabled, feature_flags, prelaunch_mode


class PrelaunchError(Exception):
    pass


def _active_questionnaire(db: Session) -> QuestionnaireVersion:
    rows = db.execute(
        select(QuestionnaireVersion).where(QuestionnaireVersion.is_active.is_(True))
    ).scalars().all()
    if len(rows) != 1:
        raise PrelaunchError("active_questionnaire_not_configured")
    return rows[0]


def own_compatibility_profile(
    db: Session,
    *,
    user_id: int,
) -> dict[str, Any]:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise PrelaunchError("profile_not_found")
    if not profile.questionnaire_completed:
        raise PrelaunchError("questionnaire_incomplete")

    version = _active_questionnaire(db)
    rows = db.execute(
        select(QuestionnaireAnswer, QuestionnaireQuestion)
        .join(
            QuestionnaireQuestion,
            QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
        )
        .where(
            QuestionnaireAnswer.user_id == user_id,
            QuestionnaireQuestion.version_id == version.id,
        )
    ).all()

    by_section: dict[str, list[int]] = defaultdict(list)
    for answer, question in rows:
        if question.answer_type != "scale" or answer.value_int is None:
            continue
        by_section[question.category].append(int(answer.value_int))

    def section_score(section: str) -> int:
        values = by_section.get(section) or []
        if not values:
            return 0
        return round(sum((value - 1) * 25 for value in values) / len(values))

    summary = {
        "Ценности": section_score("Ценности"),
        "Ориентация на семью": round(
            (section_score("Семья") + section_score("Дети")) / 2
        ),
        "Потребность в близости": section_score("Эмоциональная близость"),
        "Социальность": section_score("Социальность"),
        "Амбициозность": section_score("Работа и амбиции"),
    }
    return {
        "version": version.code,
        "summary": summary,
        "note": "Это описание ваших ответов, а не оценка личности или прогноз отношений.",
    }


def waitlist_status(
    db: Session,
    *,
    user_id: int,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    profile = db.get(Profile, user_id)
    if user is None or profile is None:
        raise PrelaunchError("profile_not_found")

    completion = profile_completion_state(profile)
    ready = (
        user.status == "ACTIVE"
        and completion["basic"]
        and completion["details"]
        and completion["readiness"]
        and completion["questionnaire"]
        and completion["partner_preferences"]
        and completion["photos"]
        and completion["profile"]
        and profile.eligibility_status == "ACTIVE_FOR_MATCHING"
        and profile.relationship_status in {"ACTIVE_SEARCH", "OPEN_TO_MATCH"}
    )

    prelaunch = prelaunch_mode(db)
    output_enabled = candidate_output_enabled(db)

    if not ready:
        state = "PROFILE_INCOMPLETE_OR_INACTIVE"
        message = "Завершите профиль и оставьте статус знакомства активным."
    elif prelaunch and not output_enabled:
        state = "WAITLIST"
        message = (
            "Профиль готов и участвует в наборе аудитории. "
            "Выдача кандидатов пока закрыта до запуска или контролируемого теста."
        )
    elif output_enabled:
        state = "MATCHING_ACTIVE"
        message = "Профиль готов к подбору кандидатов."
    else:
        state = "READY"
        message = "Профиль готов."

    return {
        "state": state,
        "ready": ready,
        "completion": completion,
        "relationship_status": profile.relationship_status,
        "eligibility_status": profile.eligibility_status,
        "features": feature_flags(db),
        "message": message,
    }
