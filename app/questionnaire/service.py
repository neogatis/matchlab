from __future__ import annotations

from collections import OrderedDict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.events import EVENT_QUESTIONNAIRE_COMPLETED, EVENT_QUESTIONNAIRE_STARTED, track_once
from app.profile.service import recompute_profile_completion
from app.db.models import (
    Profile,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    QuestionnaireVersion,
)
from .catalog_v7 import V7_QUESTIONS, V7_SCALE_OPTIONS, V7_VERSION_CODE, V7_VERSION_TITLE


class QuestionnaireError(Exception):
    pass


class QuestionnaireNotConfigured(QuestionnaireError):
    pass


class InvalidAnswer(QuestionnaireError):
    pass


def seed_v7_questionnaire(db: Session, *, activate: bool = True) -> QuestionnaireVersion:
    version = db.execute(
        select(QuestionnaireVersion).where(QuestionnaireVersion.code == V7_VERSION_CODE)
    ).scalar_one_or_none()

    if version is None:
        version = QuestionnaireVersion(
            code=V7_VERSION_CODE,
            title=V7_VERSION_TITLE,
            is_active=False,
        )
        db.add(version)
        db.flush()
    else:
        version.title = V7_VERSION_TITLE

    existing = {
        q.legacy_qid: q
        for q in db.execute(
            select(QuestionnaireQuestion).where(QuestionnaireQuestion.version_id == version.id)
        ).scalars()
    }

    for position, (legacy_qid, category, text) in enumerate(V7_QUESTIONS, start=1):
        q = existing.get(legacy_qid)
        if q is None:
            q = QuestionnaireQuestion(
                version_id=version.id,
                legacy_qid=legacy_qid,
                category=category,
                question_text=text,
                answer_type="scale",
                is_required=True,
                options_json=V7_SCALE_OPTIONS,
                weight=1,
                match_logic={
                    "scale_min": 1,
                    "scale_max": 5,
                    "legacy_formula": "100-25*abs(a-b)",
                },
                position=position,
            )
            db.add(q)
        else:
            q.category = category
            q.question_text = text
            q.answer_type = "scale"
            q.is_required = True
            q.options_json = V7_SCALE_OPTIONS
            q.weight = 1
            q.match_logic = {
                "scale_min": 1,
                "scale_max": 5,
                "legacy_formula": "100-25*abs(a-b)",
            }
            q.position = position

    if activate:
        for other in db.execute(
            select(QuestionnaireVersion).where(
                QuestionnaireVersion.id != version.id,
                QuestionnaireVersion.is_active.is_(True),
            )
        ).scalars():
            other.is_active = False
        version.is_active = True

    db.flush()
    return version


def active_version(db: Session) -> QuestionnaireVersion:
    versions = db.execute(
        select(QuestionnaireVersion)
        .where(QuestionnaireVersion.is_active.is_(True))
        .order_by(QuestionnaireVersion.id.desc())
    ).scalars().all()
    if not versions:
        raise QuestionnaireNotConfigured("No active questionnaire version")
    if len(versions) > 1:
        raise QuestionnaireNotConfigured("More than one active questionnaire version")
    return versions[0]


def questions_for_version(db: Session, version_id: int) -> list[QuestionnaireQuestion]:
    return list(
        db.execute(
            select(QuestionnaireQuestion)
            .where(QuestionnaireQuestion.version_id == version_id)
            .order_by(QuestionnaireQuestion.position)
        ).scalars()
    )


def sections(db: Session, version_id: int | None = None) -> list[dict[str, Any]]:
    version = db.get(QuestionnaireVersion, version_id) if version_id else active_version(db)
    if version is None:
        raise QuestionnaireNotConfigured("Questionnaire version not found")

    grouped: OrderedDict[str, list[QuestionnaireQuestion]] = OrderedDict()
    for q in questions_for_version(db, version.id):
        grouped.setdefault(q.category, []).append(q)

    return [
        {
            "category": category,
            "questions": [
                {
                    "id": q.id,
                    "legacy_qid": q.legacy_qid,
                    "text": q.question_text,
                    "answer_type": q.answer_type,
                    "required": q.is_required,
                    "options": q.options_json,
                    "position": q.position,
                }
                for q in items
            ],
        }
        for category, items in grouped.items()
    ]


def _normalize_answer(question: QuestionnaireQuestion, value: Any) -> tuple[int | None, str | None, Any]:
    kind = question.answer_type

    if kind == "scale":
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidAnswer("Scale answer must be an integer")
        minimum = int((question.match_logic or {}).get("scale_min", 1))
        maximum = int((question.match_logic or {}).get("scale_max", 5))
        if not minimum <= value <= maximum:
            raise InvalidAnswer(f"Scale answer must be between {minimum} and {maximum}")
        return value, None, None

    if kind in {"single", "priority"}:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise InvalidAnswer(f"{kind} answer must be scalar")
        allowed = question.options_json or []
        allowed_values = {
            item.get("value") if isinstance(item, dict) else item
            for item in allowed
        }
        if allowed and value not in allowed_values:
            raise InvalidAnswer("Answer is not one of the configured options")
        return None, str(value), None

    if kind == "multiple":
        if not isinstance(value, list):
            raise InvalidAnswer("Multiple answer must be a list")
        if len(value) != len(set(map(str, value))):
            raise InvalidAnswer("Multiple answer contains duplicates")
        allowed = question.options_json or []
        allowed_values = {
            str(item.get("value") if isinstance(item, dict) else item)
            for item in allowed
        }
        if allowed and any(str(v) not in allowed_values for v in value):
            raise InvalidAnswer("Answer contains an unsupported option")
        return None, None, value

    if kind == "text":
        if not isinstance(value, str):
            raise InvalidAnswer("Text answer must be text")
        value = value.strip()
        if len(value) > 2000:
            raise InvalidAnswer("Text answer is too long")
        if question.is_required and not value:
            raise InvalidAnswer("Answer is required")
        return None, value or None, None

    raise InvalidAnswer("Unsupported answer type")


def save_answer(
    db: Session,
    *,
    user_id: int,
    question_id: int,
    value: Any,
) -> QuestionnaireAnswer:
    version = active_version(db)
    question = db.get(QuestionnaireQuestion, question_id)
    if question is None or question.version_id != version.id:
        raise QuestionnaireError("Question is not part of the active questionnaire")

    profile = db.get(Profile, user_id)
    if profile is None:
        raise QuestionnaireError("Profile not found")

    value_int, value_text, value_json = _normalize_answer(question, value)
    answer = db.get(QuestionnaireAnswer, (user_id, question_id))
    if answer is None:
        answer = QuestionnaireAnswer(user_id=user_id, question_id=question_id)
        db.add(answer)

    answer.value_int = value_int
    answer.value_text = value_text
    answer.value_json = value_json
    db.flush()
    track_once(
        db,
        event_type=EVENT_QUESTIONNAIRE_STARTED,
        user_id=user_id,
        metadata={"questionnaire_version": version.code},
    )
    completed = recompute_completion(db, user_id=user_id, version_id=version.id)
    if completed:
        track_once(
            db,
            event_type=EVENT_QUESTIONNAIRE_COMPLETED,
            user_id=user_id,
            metadata={"questionnaire_version": version.code},
        )
    return answer


def save_answers(
    db: Session,
    *,
    user_id: int,
    answers: dict[int, Any],
) -> dict[str, Any]:
    if not answers:
        return progress(db, user_id=user_id)

    for question_id, value in answers.items():
        save_answer(db, user_id=user_id, question_id=int(question_id), value=value)
    return progress(db, user_id=user_id)


def progress(db: Session, *, user_id: int, version_id: int | None = None) -> dict[str, Any]:
    version = db.get(QuestionnaireVersion, version_id) if version_id else active_version(db)
    if version is None:
        raise QuestionnaireNotConfigured("Questionnaire version not found")

    required_total = db.scalar(
        select(func.count())
        .select_from(QuestionnaireQuestion)
        .where(
            QuestionnaireQuestion.version_id == version.id,
            QuestionnaireQuestion.is_required.is_(True),
        )
    ) or 0

    answered_required = db.scalar(
        select(func.count())
        .select_from(QuestionnaireAnswer)
        .join(
            QuestionnaireQuestion,
            QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
        )
        .where(
            QuestionnaireAnswer.user_id == user_id,
            QuestionnaireQuestion.version_id == version.id,
            QuestionnaireQuestion.is_required.is_(True),
        )
    ) or 0

    all_total = db.scalar(
        select(func.count())
        .select_from(QuestionnaireQuestion)
        .where(QuestionnaireQuestion.version_id == version.id)
    ) or 0

    answered_total = db.scalar(
        select(func.count())
        .select_from(QuestionnaireAnswer)
        .join(
            QuestionnaireQuestion,
            QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
        )
        .where(
            QuestionnaireAnswer.user_id == user_id,
            QuestionnaireQuestion.version_id == version.id,
        )
    ) or 0

    complete = required_total > 0 and answered_required == required_total
    percent = 0 if required_total == 0 else int(round(answered_required * 100 / required_total))
    return {
        "version": version.code,
        "required_total": int(required_total),
        "required_answered": int(answered_required),
        "total": int(all_total),
        "answered": int(answered_total),
        "percent": percent,
        "complete": complete,
    }


def recompute_completion(db: Session, *, user_id: int, version_id: int | None = None) -> bool:
    state = progress(db, user_id=user_id, version_id=version_id)
    profile = db.get(Profile, user_id)
    if profile is None:
        raise QuestionnaireError("Profile not found")
    profile.questionnaire_completed = bool(state["complete"])
    db.flush()
    recompute_profile_completion(db, user_id=user_id)
    return profile.questionnaire_completed
