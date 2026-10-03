from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.events import (
    EVENT_QUESTIONNAIRE_COMPLETED,
    EVENT_QUESTIONNAIRE_STARTED,
    track_once,
)
from app.db.models import (
    AdaptiveQuestionnaireAnswer,
    AdaptiveQuestionnaireQuestion,
    Profile,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
)
from app.profile.service import recompute_profile_completion
from .service import active_version


ADAPTIVE_VERSION = "adaptive-v1"
MIN_ADAPTIVE_ANSWERS = 8
MAX_ADAPTIVE_ANSWERS = 20
QUEUE_SIZE = 4

SCALE_OPTIONS = [
    {"value": 1, "label": "Совсем не похоже на меня"},
    {"value": 2, "label": "Скорее не похоже"},
    {"value": 3, "label": "Зависит от ситуации"},
    {"value": 4, "label": "Скорее похоже"},
    {"value": 5, "label": "Очень похоже на меня"},
]


@dataclass(frozen=True)
class Axis:
    key: str
    label: str
    category_key: str
    high_definition: str
    legacy_qids: tuple[int, int]


AXES: tuple[Axis, ...] = (
    Axis(
        "self_awareness",
        "Самопонимание",
        "personality_score",
        "человек хорошо понимает собственные потребности, ритм и жизненные цели",
        (1, 4),
    ),
    Axis(
        "emotional_regulation",
        "Эмоциональная устойчивость",
        "personality_score",
        "человек сохраняет самообладание и принимает важные решения без импульсивности",
        (5, 8),
    ),
    Axis(
        "trust_honesty",
        "Честность и договорённости",
        "values_score",
        "человек предпочитает прямую честность и считает договорённости значимыми",
        (9, 10),
    ),
    Axis(
        "relationship_structure",
        "Партнёрство",
        "relationship_score",
        "человек воспринимает отношения как команду и предпочитает ясно обсуждать ожидания",
        (13, 15),
    ),
    Axis(
        "closeness_need",
        "Потребность в близости",
        "relationship_score",
        "человеку нужен регулярный эмоциональный контакт, внимание и разговор о чувствах",
        (14, 49),
    ),
    Axis(
        "autonomy_need",
        "Личное пространство",
        "personality_score",
        "человеку важно сохранять автономность и время отдельно от партнёра",
        (41, 43),
    ),
    Axis(
        "conflict_repair",
        "Поведение в конфликте",
        "communication_score",
        "человек стремится обсуждать конфликт уважительно, признавать ошибки и восстанавливать контакт",
        (45, 47),
    ),
    Axis(
        "family_orientation",
        "Семейность",
        "family_score",
        "человек хочет включённости партнёра в семейную жизнь и совместных бытовых решений",
        (17, 20),
    ),
    Axis(
        "parenthood_orientation",
        "Отношение к детям",
        "family_score",
        "человек рассматривает тему детей как важную часть долгосрочного будущего",
        (21, 24),
    ),
    Axis(
        "ambition_drive",
        "Амбиции и самостоятельные цели",
        "future_score",
        "человеку важны профессиональный рост и собственные цели вне отношений",
        (25, 27),
    ),
    Axis(
        "financial_structure",
        "Финансовая организованность",
        "values_score",
        "человек предпочитает открыто обсуждать деньги и иметь финансовый запас",
        (29, 31),
    ),
    Axis(
        "social_energy",
        "Социальность",
        "communication_score",
        "человека заряжают встречи, компании и активная социальная жизнь",
        (37, 39),
    ),
    Axis(
        "future_planning",
        "Планирование будущего",
        "future_score",
        "человеку комфортно заранее обсуждать место жизни и строить совместные планы на годы",
        (61, 63),
    ),
    Axis(
        "lifestyle_energy",
        "Темп жизни",
        "lifestyle_score",
        "человек предпочитает активный ритм и движение в повседневной жизни",
        (33, 35),
    ),
    Axis(
        "shared_exploration",
        "Совместные интересы",
        "interests_score",
        "человеку нравится пробовать новое вместе и интересоваться увлечениями партнёра",
        (53, 55),
    ),
)

AXIS_BY_KEY = {axis.key: axis for axis in AXES}
AXIS_BY_QID = {
    qid: axis
    for axis in AXES
    for qid in axis.legacy_qids
}

BASE_ORDER = (
    1, 5, 9, 13, 14, 41, 45, 17, 21, 25, 29, 37, 61, 33, 53,
    4, 8, 10, 15, 49, 43, 47, 20, 24, 27, 31, 39, 63, 35, 55,
)

BASE_TEXT_OVERRIDES = {
    1: "Когда думаю о своей обычной неделе, я понимаю, какой ритм жизни делает меня счастливее.",
    4: "У меня есть довольно ясное представление, как я хочу жить через несколько лет.",
    5: "Когда планы внезапно меняются, я обычно сохраняю спокойствие.",
    8: "В важных решениях я скорее беру паузу и обдумываю, чем действую сгоряча.",
    9: "Даже если правда может вызвать неприятный разговор, я предпочту сказать честно.",
    10: "Если мы о чём-то договорились, для меня важно выполнить это даже после ссоры.",
    13: "В отношениях мне ближе ощущение «мы — команда», чем каждый сам по себе.",
    15: "Мне спокойнее, когда важные ожидания в отношениях проговорены прямо.",
    14: "Мне нужен регулярный контакт и знаки внимания от партнёра.",
    49: "Мне естественно говорить с близким человеком о том, что я чувствую.",
    41: "Чтобы чувствовать себя хорошо, мне регулярно нужно время только для себя.",
    43: "Даже в близких отношениях мне не нужен постоянный контакт в течение всего дня.",
    45: "Даже когда я злюсь, мне важно обсуждать проблему без унижений и оскорблений.",
    47: "Если понимаю, что был(а) неправ(а), мне обычно несложно это признать.",
    17: "Для меня серьёзные отношения естественно включают участие в семейной жизни.",
    20: "Бытовые и семейные решения я предпочитаю принимать вместе, а не делить на «твоё» и «моё».",
    21: "Я представляю детей частью своего будущего.",
    24: "Разговор о детях для меня должен случиться до того, как отношения станут очень серьёзными.",
    25: "Мне важно продолжать профессионально расти, даже находясь в отношениях.",
    27: "Даже в счастливых отношениях мне нужны собственные цели и проекты.",
    29: "Я могу спокойно обсуждать с партнёром доходы, расходы и финансовые ошибки.",
    31: "Мне спокойнее, когда есть финансовый запас на непредвиденные ситуации.",
    37: "После насыщенной недели мне обычно хочется увидеться с друзьями, а не побыть одному.",
    39: "Большая компания или мероприятие чаще заряжает меня, чем утомляет.",
    61: "Если отношения становятся серьёзными, мне важно заранее обсудить, где мы хотим жить.",
    63: "Мне комфортно строить с партнёром планы на несколько лет вперёд.",
    33: "Регулярная физическая активность — естественная часть моей жизни.",
    35: "В свободный день я чаще выберу движение или поездку, чем спокойный отдых дома.",
    53: "Мне нравится вместе с партнёром пробовать то, чего мы оба раньше не делали.",
    55: "Мне интересно погружаться в увлечения партнёра, даже если сначала они мне непонятны.",
}

BANK: dict[str, tuple[str, ...]] = {
    "self_awareness": (
        "Когда мне что-то не подходит в отношениях, я обычно довольно быстро понимаю, что именно меня задело.",
        "Мне легко отличить собственное желание от того, что от меня ожидают другие.",
        "Перед важным решением я обычно понимаю, какая моя потребность стоит за этим выбором.",
    ),
    "emotional_regulation": (
        "Если разговор становится напряжённым, я могу сделать паузу и вернуться к нему спокойнее.",
        "Сильная эмоция редко заставляет меня принимать решение, о котором потом жалею.",
        "Когда происходит что-то неожиданное, мне обычно удаётся сначала разобраться, а потом реагировать.",
    ),
    "trust_honesty": (
        "Если я совершил(а) ошибку, которая может расстроить партнёра, я предпочту рассказать сам(а).",
        "Мне трудно чувствовать близость, если важные темы приходится обходить молчанием.",
        "Даже небольшие обещания для меня имеют значение, если на них рассчитывает близкий человек.",
    ),
    "relationship_structure": (
        "Если у пары появляется серьёзная проблема, я скорее ищу решение «для нас», чем защищаю только свою позицию.",
        "Мне комфортно прямо договариваться о том, что каждый ждёт от отношений.",
        "В серьёзной паре мне важно чувствовать, что решения принимаются с учётом обоих.",
    ),
    "closeness_need": (
        "Если близкий человек почти не выходит на связь весь день, мне обычно не хватает контакта.",
        "Мне важно регулярно слышать от партнёра, что происходит у него внутри, а не только обсуждать дела.",
        "Тёплые сообщения и небольшие проявления внимания заметно влияют на моё ощущение близости.",
    ),
    "autonomy_need": (
        "Даже в очень близких отношениях мне важно иногда проводить вечер отдельно.",
        "Мне комфортно, если у партнёра есть друзья и занятия, в которых я почти не участвую.",
        "Я лучше чувствую себя в отношениях, когда у каждого сохраняется часть собственной жизни.",
    ),
    "conflict_repair": (
        "После серьёзной ссоры для меня важно вернуться к разговору и понять, что произошло.",
        "Если партнёр говорит, что я его задел(а), я стараюсь сначала понять его, а не сразу защищаться.",
        "Мне проще решать разногласие, когда мы обсуждаем конкретную проблему, а не вспоминаем старые ошибки.",
    ),
    "family_orientation": (
        "Если отношения серьёзные, мне важно постепенно становиться частью семейной жизни друг друга.",
        "Мне близка идея, что бытовые обязанности в паре обсуждаются и распределяются совместно.",
        "Для меня семейные решения — это область, где мнение партнёра должно реально влиять на итог.",
    ),
    "parenthood_orientation": (
        "Тема того, будут ли у нас дети, для меня слишком важна, чтобы оставлять её «на потом».",
        "При выборе долгосрочного партнёра его отношение к родительству для меня имеет большое значение.",
        "Я готов(а) учитывать, как будущая семья с детьми изменит привычный образ жизни.",
    ),
    "ambition_drive": (
        "Мне важно продолжать развивать собственную карьеру или дело, даже если отношения занимают много места в жизни.",
        "Я лучше чувствую себя рядом с человеком, у которого тоже есть собственные цели.",
        "Если ради отношений приходится полностью отказаться от личных планов, мне это будет тяжело.",
    ),
    "financial_structure": (
        "Перед крупной совместной покупкой мне важно заранее обсудить бюджет и последствия.",
        "Мне комфортнее, когда в паре нет скрытых долгов или крупных финансовых обязательств.",
        "Я скорее отложу часть дохода в запас, чем потрачу всё на текущие желания.",
    ),
    "social_energy": (
        "Несколько встреч с людьми подряд чаще дают мне энергию, чем заставляют восстанавливаться в одиночестве.",
        "Мне нравится, когда в жизни пары есть друзья, гости и совместные компании.",
        "Новое знакомство обычно вызывает у меня больше интереса, чем напряжения.",
    ),
    "future_planning": (
        "Если отношения серьёзные, мне хочется понимать, куда мы движемся в ближайшие несколько лет.",
        "Мне комфортнее, когда важные жизненные перемены мы обсуждаем заранее.",
        "Неопределённость о будущем пары надолго обычно начинает меня беспокоить.",
    ),
    "lifestyle_energy": (
        "Когда есть свободное время, мне чаще хочется куда-то выбраться, чем провести весь день дома.",
        "Мне легче поддерживать хорошее самочувствие, когда в неделе есть движение и активность.",
        "Я предпочитаю насыщенный ритм жизни слишком спокойному и однообразному.",
    ),
    "shared_exploration": (
        "Мне нравится, когда у пары регулярно появляются новые совместные впечатления.",
        "Я готов(а) попробовать увлечение партнёра хотя бы ради того, чтобы лучше его понять.",
        "Для меня совместные открытия сближают сильнее, чем просто привычный одинаковый досуг.",
    ),
}


class AdaptiveQuestionnaireError(Exception):
    pass


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _legacy_answers_by_qid(db: Session, user_id: int) -> dict[int, int]:
    version = active_version(db)
    rows = db.execute(
        select(QuestionnaireQuestion.legacy_qid, QuestionnaireAnswer.value_int)
        .join(
            QuestionnaireAnswer,
            QuestionnaireAnswer.question_id == QuestionnaireQuestion.id,
        )
        .where(
            QuestionnaireAnswer.user_id == user_id,
            QuestionnaireQuestion.version_id == version.id,
            QuestionnaireAnswer.value_int.is_not(None),
        )
    ).all()
    return {
        int(qid): int(value)
        for qid, value in rows
        if qid is not None and value is not None
    }


def _adaptive_values_by_axis(db: Session, user_id: int) -> dict[str, list[int]]:
    rows = db.execute(
        select(
            AdaptiveQuestionnaireQuestion.axis_key,
            AdaptiveQuestionnaireAnswer.value_int,
        )
        .join(
            AdaptiveQuestionnaireAnswer,
            AdaptiveQuestionnaireAnswer.adaptive_question_id
            == AdaptiveQuestionnaireQuestion.id,
        )
        .where(AdaptiveQuestionnaireAnswer.user_id == user_id)
    ).all()
    out: dict[str, list[int]] = {}
    for axis_key, value in rows:
        out.setdefault(str(axis_key), []).append(int(value))
    return out


def trait_snapshot(db: Session, *, user_id: int) -> dict[str, dict[str, Any]]:
    legacy = _legacy_answers_by_qid(db, user_id)
    adaptive = _adaptive_values_by_axis(db, user_id)
    out: dict[str, dict[str, Any]] = {}

    for axis in AXES:
        values = [
            int(legacy[qid])
            for qid in axis.legacy_qids
            if qid in legacy
        ] + list(adaptive.get(axis.key, []))

        if not values:
            out[axis.key] = {
                "key": axis.key,
                "label": axis.label,
                "category_key": axis.category_key,
                "score": None,
                "confidence": 0.0,
                "samples": 0,
            }
            continue

        mean = sum(values) / len(values)
        score = int(round((mean - 1.0) * 25.0))
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance)
        consistency = _clamp(1.0 - (std / 2.0), 0.20, 1.0)
        sample_factor = min(1.0, len(values) / 4.0)
        confidence = round(sample_factor * consistency, 3)

        out[axis.key] = {
            "key": axis.key,
            "label": axis.label,
            "category_key": axis.category_key,
            "score": max(0, min(100, score)),
            "confidence": confidence,
            "samples": len(values),
        }

    return out


def _legacy_complete(db: Session, user_id: int) -> bool:
    version = active_version(db)
    answered = db.scalar(
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
    required = db.scalar(
        select(func.count())
        .select_from(QuestionnaireQuestion)
        .where(
            QuestionnaireQuestion.version_id == version.id,
            QuestionnaireQuestion.is_required.is_(True),
        )
    ) or 0
    return required >= 60 and answered >= required


def _base_answered(legacy: dict[int, int]) -> int:
    return sum(1 for qid in BASE_ORDER if qid in legacy)


def _adaptive_answered_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AdaptiveQuestionnaireAnswer)
            .where(AdaptiveQuestionnaireAnswer.user_id == user_id)
        )
        or 0
    )


def _adaptive_generated_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AdaptiveQuestionnaireQuestion)
            .where(AdaptiveQuestionnaireQuestion.user_id == user_id)
        )
        or 0
    )


def _should_finish(snapshot: dict[str, dict[str, Any]], adaptive_answered: int) -> bool:
    if adaptive_answered >= MAX_ADAPTIVE_ANSWERS:
        return True
    if adaptive_answered < MIN_ADAPTIVE_ANSWERS:
        return False
    uncertain = sum(
        1
        for item in snapshot.values()
        if float(item["confidence"]) < 0.58
    )
    return uncertain <= 3


def _portrait(snapshot: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "key": axis.key,
            "label": axis.label,
            "score": snapshot[axis.key]["score"],
            "confidence_percent": int(
                round(float(snapshot[axis.key]["confidence"]) * 100)
            ),
            "samples": int(snapshot[axis.key]["samples"]),
        }
        for axis in AXES
    ]


def _base_question(db: Session, qid: int) -> QuestionnaireQuestion:
    version = active_version(db)
    row = db.execute(
        select(QuestionnaireQuestion).where(
            QuestionnaireQuestion.version_id == version.id,
            QuestionnaireQuestion.legacy_qid == qid,
        )
    ).scalar_one_or_none()
    if row is None:
        raise AdaptiveQuestionnaireError(
            f"Base questionnaire question {qid} is not configured"
        )
    return row


def _serialize_base_question(db: Session, qid: int) -> dict[str, Any]:
    question = _base_question(db, qid)
    axis = AXIS_BY_QID[qid]
    return {
        "token": f"base:{question.id}",
        "kind": "base",
        "axis_key": axis.key,
        "axis_label": axis.label,
        "text": BASE_TEXT_OVERRIDES.get(qid, question.question_text),
        "options": SCALE_OPTIONS,
    }


def _serialize_adaptive_question(
    question: AdaptiveQuestionnaireQuestion,
) -> dict[str, Any]:
    axis = AXIS_BY_KEY[question.axis_key]
    return {
        "token": f"adaptive:{question.id}",
        "kind": "adaptive",
        "axis_key": axis.key,
        "axis_label": axis.label,
        "text": question.prompt_text,
        "options": SCALE_OPTIONS,
        "source": question.source,
    }


def _unanswered_generated(
    db: Session,
    user_id: int,
) -> list[AdaptiveQuestionnaireQuestion]:
    answered_ids = select(
        AdaptiveQuestionnaireAnswer.adaptive_question_id
    ).where(AdaptiveQuestionnaireAnswer.user_id == user_id)
    return list(
        db.execute(
            select(AdaptiveQuestionnaireQuestion)
            .where(
                AdaptiveQuestionnaireQuestion.user_id == user_id,
                AdaptiveQuestionnaireQuestion.id.not_in(answered_ids),
            )
            .order_by(AdaptiveQuestionnaireQuestion.position)
        ).scalars()
    )


def _priority_axes(
    snapshot: dict[str, dict[str, Any]],
    *,
    limit: int,
) -> list[Axis]:
    ranked = sorted(
        AXES,
        key=lambda axis: (
            float(snapshot[axis.key]["confidence"]),
            int(snapshot[axis.key]["samples"]),
            axis.key,
        ),
    )
    return ranked[:limit]


def _bank_text(
    axis: Axis,
    *,
    user_id: int,
    position: int,
) -> str:
    items = BANK[axis.key]
    index = (user_id + position + len(axis.key)) % len(items)
    return items[index]


def _extract_response_text(payload: dict[str, Any]) -> str | None:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text")
    return None


def _openai_batch(
    axes: list[Axis],
    snapshot: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, str]], str | None]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_ADAPTIVE_MODEL", "").strip()
    if not api_key or not model or not axes:
        return [], None

    axis_payload = [
        {
            "axis_key": axis.key,
            "label": axis.label,
            "high_definition": axis.high_definition,
            "score": snapshot[axis.key]["score"],
            "confidence": snapshot[axis.key]["confidence"],
            "samples": snapshot[axis.key]["samples"],
        }
        for axis in axes
    ]
    allowed = [axis.key for axis in axes]
    schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": len(axes),
                "maxItems": len(axes),
                "items": {
                    "type": "object",
                    "properties": {
                        "axis_key": {
                            "type": "string",
                            "enum": allowed,
                        },
                        "text": {
                            "type": "string",
                            "minLength": 20,
                            "maxLength": 220,
                        },
                    },
                    "required": ["axis_key", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    }
    instructions = (
        "Ты формулируешь уточняющие вопросы для дейтинг-анкеты MatchLab. "
        "Это не медицинская и не диагностическая оценка. "
        "Для каждой переданной психологической оси создай ровно одно короткое, "
        "естественное и конкретное утверждение или бытовой сценарий на русском языке. "
        "Пользователь отвечает по шкале от 1 «совсем не похоже на меня» до 5 "
        "«очень похоже на меня». Формулируй так, чтобы более высокий ответ всегда "
        "означал БОЛЬШЕ признака из high_definition. Не упоминай названия шкал, "
        "психологические диагнозы, типы личности, травмы или клинические термины. "
        "Не задавай вопрос, который уже очевидно повторяет предыдущий смысл. "
        "Верни только структуру по заданной JSON-схеме."
    )
    body = {
        "model": model,
        "store": False,
        "max_output_tokens": 700,
        "instructions": instructions,
        "input": json.dumps(
            {
                "task": "generate_adaptive_relationship_questions",
                "axes": axis_payload,
            },
            ensure_ascii=False,
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "adaptive_questions",
                "strict": True,
                "schema": schema,
            }
        },
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        raw = _extract_response_text(payload)
        if not raw:
            return [], model
        parsed = json.loads(raw)
        questions = parsed.get("questions") or []
    except Exception:
        return [], model

    seen: set[str] = set()
    valid: list[dict[str, str]] = []
    for item in questions:
        axis_key = str(item.get("axis_key", ""))
        text = str(item.get("text", "")).strip()
        if (
            axis_key in allowed
            and axis_key not in seen
            and 20 <= len(text) <= 220
        ):
            seen.add(axis_key)
            valid.append({"axis_key": axis_key, "text": text})
    return valid, model


def _ensure_queue(
    db: Session,
    *,
    user_id: int,
    snapshot: dict[str, dict[str, Any]],
) -> None:
    unanswered = _unanswered_generated(db, user_id)
    if unanswered:
        return

    answered = _adaptive_answered_count(db, user_id)
    if _should_finish(snapshot, answered):
        return

    remaining = MAX_ADAPTIVE_ANSWERS - _adaptive_generated_count(db, user_id)
    if remaining <= 0:
        return

    batch_size = min(QUEUE_SIZE, remaining)
    axes = _priority_axes(snapshot, limit=batch_size)
    generated, model = _openai_batch(axes, snapshot)
    generated_map = {
        item["axis_key"]: item["text"]
        for item in generated
    }

    position = _adaptive_generated_count(db, user_id)
    for axis in axes:
        position += 1
        text = generated_map.get(axis.key)
        source = "OPENAI" if text else "BANK"
        if not text:
            text = _bank_text(
                axis,
                user_id=user_id,
                position=position,
            )
        db.add(
            AdaptiveQuestionnaireQuestion(
                user_id=user_id,
                axis_key=axis.key,
                category_key=axis.category_key,
                prompt_text=text,
                source=source,
                model=model if source == "OPENAI" else None,
                position=position,
                generator_metadata={
                    "adaptive_version": ADAPTIVE_VERSION,
                    "confidence_before": snapshot[axis.key]["confidence"],
                    "score_before": snapshot[axis.key]["score"],
                },
            )
        )
    db.flush()


def _mark_complete(db: Session, user_id: int) -> None:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise AdaptiveQuestionnaireError("Profile not found")
    if not profile.questionnaire_completed:
        profile.questionnaire_completed = True
        track_once(
            db,
            event_type=EVENT_QUESTIONNAIRE_COMPLETED,
            user_id=user_id,
            metadata={"questionnaire_version": ADAPTIVE_VERSION},
        )
    db.flush()
    recompute_profile_completion(db, user_id=user_id)


def state(
    db: Session,
    *,
    user_id: int,
    generate_queue: bool = True,
) -> dict[str, Any]:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise AdaptiveQuestionnaireError("Profile not found")

    if _legacy_complete(db, user_id):
        snapshot = trait_snapshot(db, user_id=user_id)
        return {
            "mode": ADAPTIVE_VERSION,
            "phase": "COMPLETE",
            "complete": True,
            "legacy_complete": True,
            "progress": {
                "base_answered": len(BASE_ORDER),
                "base_total": len(BASE_ORDER),
                "adaptive_answered": 0,
                "adaptive_min": MIN_ADAPTIVE_ANSWERS,
                "adaptive_max": MAX_ADAPTIVE_ANSWERS,
                "percent": 100,
            },
            "portrait": _portrait(snapshot),
            "question": None,
            "prefetch": [],
        }

    legacy = _legacy_answers_by_qid(db, user_id)
    base_answered = _base_answered(legacy)
    snapshot = trait_snapshot(db, user_id=user_id)
    adaptive_answered = _adaptive_answered_count(db, user_id)

    if base_answered < len(BASE_ORDER):
        qid = next(qid for qid in BASE_ORDER if qid not in legacy)
        percent = int(round(base_answered * 70 / len(BASE_ORDER)))
        remaining_qids = [
            item
            for item in BASE_ORDER
            if item not in legacy
        ][:QUEUE_SIZE]
        serialized = [
            _serialize_base_question(db, item)
            for item in remaining_qids
        ]
        return {
            "mode": ADAPTIVE_VERSION,
            "phase": "BASE",
            "complete": False,
            "legacy_complete": False,
            "progress": {
                "base_answered": base_answered,
                "base_total": len(BASE_ORDER),
                "adaptive_answered": adaptive_answered,
                "adaptive_min": MIN_ADAPTIVE_ANSWERS,
                "adaptive_max": MAX_ADAPTIVE_ANSWERS,
                "percent": percent,
            },
            "portrait": _portrait(snapshot),
            "question": serialized[0],
            "prefetch": serialized[1:],
        }

    if _should_finish(snapshot, adaptive_answered):
        _mark_complete(db, user_id)
        return {
            "mode": ADAPTIVE_VERSION,
            "phase": "COMPLETE",
            "complete": True,
            "legacy_complete": False,
            "progress": {
                "base_answered": base_answered,
                "base_total": len(BASE_ORDER),
                "adaptive_answered": adaptive_answered,
                "adaptive_min": MIN_ADAPTIVE_ANSWERS,
                "adaptive_max": MAX_ADAPTIVE_ANSWERS,
                "percent": 100,
            },
            "portrait": _portrait(snapshot),
            "question": None,
        }

    if generate_queue:
        _ensure_queue(
            db,
            user_id=user_id,
            snapshot=snapshot,
        )

    pending = _unanswered_generated(db, user_id)
    if not pending:
        raise AdaptiveQuestionnaireError("Adaptive question queue is empty")

    estimated_total = len(BASE_ORDER) + max(
        MIN_ADAPTIVE_ANSWERS,
        adaptive_answered + len(pending),
    )
    answered_total = base_answered + adaptive_answered
    percent = min(
        99,
        int(round(answered_total * 100 / max(1, estimated_total))),
    )
    return {
        "mode": ADAPTIVE_VERSION,
        "phase": "ADAPTIVE",
        "complete": False,
        "legacy_complete": False,
        "progress": {
            "base_answered": base_answered,
            "base_total": len(BASE_ORDER),
            "adaptive_answered": adaptive_answered,
            "adaptive_min": MIN_ADAPTIVE_ANSWERS,
            "adaptive_max": MAX_ADAPTIVE_ANSWERS,
            "percent": percent,
        },
        "portrait": _portrait(snapshot),
        "question": _serialize_adaptive_question(pending[0]),
        "prefetch": [
            _serialize_adaptive_question(item)
            for item in pending[1:QUEUE_SIZE]
        ],
    }


def answer(
    db: Session,
    *,
    user_id: int,
    question_token: str,
    value: int,
) -> dict[str, Any]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 5:
        raise AdaptiveQuestionnaireError("Answer must be an integer between 1 and 5")

    profile = db.get(Profile, user_id)
    if profile is None:
        raise AdaptiveQuestionnaireError("Profile not found")

    try:
        kind, raw_id = question_token.split(":", 1)
        question_id = int(raw_id)
    except Exception as exc:
        raise AdaptiveQuestionnaireError("Invalid question token") from exc

    if kind == "base":
        question = db.get(QuestionnaireQuestion, question_id)
        version = active_version(db)
        if (
            question is None
            or question.version_id != version.id
            or question.legacy_qid not in BASE_ORDER
        ):
            raise AdaptiveQuestionnaireError("Invalid base question")

        row = db.get(QuestionnaireAnswer, (user_id, question.id))
        if row is None:
            row = QuestionnaireAnswer(
                user_id=user_id,
                question_id=question.id,
            )
            db.add(row)
        row.value_int = value
        row.value_text = None
        row.value_json = None
        db.flush()

    elif kind == "adaptive":
        question = db.get(AdaptiveQuestionnaireQuestion, question_id)
        if question is None or question.user_id != user_id:
            raise AdaptiveQuestionnaireError("Invalid adaptive question")
        row = db.get(
            AdaptiveQuestionnaireAnswer,
            (user_id, question.id),
        )
        if row is None:
            row = AdaptiveQuestionnaireAnswer(
                user_id=user_id,
                adaptive_question_id=question.id,
                value_int=value,
            )
            db.add(row)
        else:
            row.value_int = value
        db.flush()
    else:
        raise AdaptiveQuestionnaireError("Invalid question kind")

    track_once(
        db,
        event_type=EVENT_QUESTIONNAIRE_STARTED,
        user_id=user_id,
        metadata={"questionnaire_version": ADAPTIVE_VERSION},
    )

    return state(
        db,
        user_id=user_id,
        generate_queue=True,
    )


def adaptive_category_scores(
    db: Session,
    *,
    user_a: int,
    user_b: int,
) -> dict[str, int]:
    a = trait_snapshot(db, user_id=user_a)
    b = trait_snapshot(db, user_id=user_b)
    grouped: dict[str, list[float]] = {}

    for axis in AXES:
        av = a[axis.key]["score"]
        bv = b[axis.key]["score"]
        ac = float(a[axis.key]["confidence"])
        bc = float(b[axis.key]["confidence"])
        if av is None or bv is None:
            continue
        if min(ac, bc) < 0.35:
            continue
        similarity = max(0.0, 100.0 - abs(float(av) - float(bv)))
        confidence_weight = max(0.1, min(ac, bc))
        grouped.setdefault(axis.category_key, []).append(
            similarity * confidence_weight
        )
        grouped.setdefault(axis.category_key + "__weights", []).append(
            confidence_weight
        )

    result: dict[str, int] = {}
    for category in {
        axis.category_key
        for axis in AXES
    }:
        values = grouped.get(category, [])
        weights = grouped.get(category + "__weights", [])
        if values and weights:
            result[category] = int(round(sum(values) / sum(weights)))
    return result


def has_adaptive_answers(db: Session, *, user_id: int) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(AdaptiveQuestionnaireAnswer)
            .where(AdaptiveQuestionnaireAnswer.user_id == user_id)
        )
        or 0
    )
