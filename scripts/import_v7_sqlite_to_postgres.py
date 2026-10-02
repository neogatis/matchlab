#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.questionnaire.catalog_v7 import V7_QUESTIONS, V7_SCALE_OPTIONS, V7_VERSION_CODE, V7_VERSION_TITLE  # noqa: E402
from app.db.models import (  # noqa: E402
    Block,
    Conversation,
    DateProposal,
    Interest,
    LegacyPartnerCriteria,
    LegacyPhotoBlob,
    MarketingAttribution,
    Match,
    Message,
    Notification,
    PartnerPreference,
    Photo,
    ProductEvent,
    Profile,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    QuestionnaireVersion,
    Report,
    Session as DbSession,
    Setting,
    User,
    UserStatusHistory,
)
from app.db.session import make_engine  # noqa: E402


def parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def rows(conn: sqlite3.Connection, table: str):
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]


def json_value(value, default):
    try:
        return json.loads(value) if value not in (None, "") else default
    except Exception:
        return default


IMPORTANCE = {
    "REQUIRED": "HARD",
    "IMPORTANT": "IMPORTANT",
    "UNIMPORTANT": "IGNORE",
    "": "IGNORE",
    None: "IGNORE",
}


def add_preference(session: Session, user_id: int, key: str, spec: dict):
    importance = IMPORTANCE.get(spec.get("importance"), "IGNORE")
    kwargs = {
        "user_id": user_id,
        "criterion_key": key,
        "importance": importance,
    }
    if key in {"age", "height"}:
        kwargs["min_value"] = spec.get("min")
        kwargs["max_value"] = spec.get("max")
    elif key == "city":
        kwargs["value_text"] = str(spec.get("value") or "")
        kwargs["values_json"] = {"allow_other_city": bool(spec.get("allow_other_city"))}
    else:
        value = spec.get("value")
        if value is not None:
            kwargs["value_text"] = str(value)
    session.add(PartnerPreference(**kwargs))


def sync_sequences(session: Session):
    for table in [
        "users",
        "questionnaire_versions",
        "questionnaire_questions",
        "photos",
        "matches",
        "conversations",
        "messages",
        "date_proposals",
        "reports",
        "notifications",
        "product_events",
    ]:
        session.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 0), 1),
                    COALESCE((SELECT MAX(id) FROM {table}), 0) > 0
                )
                """
            )
        )


def import_database(sqlite_path: str, postgres_url: str):
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    engine = make_engine(postgres_url)

    with Session(engine) as session:
        existing = session.scalar(select(func.count()).select_from(User))
        if existing:
            raise RuntimeError("target PostgreSQL database is not empty; refusing to import")

        for r in rows(source, "users"):
            session.add(
                User(
                    id=r["id"],
                    email=r["email"],
                    password_hash=r["password_hash"],
                    created_at=parse_dt(r["created_at"]),
                    referral_code=r["referral_code"],
                    referred_by=r["referred_by"],
                    invites_sent=r["invites_sent"] or 0,
                )
            )
        session.flush()

        for r in rows(source, "sessions"):
            created = parse_dt(r["created_at"])
            secret_hash = hashlib.sha256(r["token"].encode("utf-8")).hexdigest()
            session.add(
                DbSession(
                    token="legacy:" + secret_hash[:32],
                    user_id=r["user_id"],
                    secret_hash=secret_hash,
                    created_at=created,
                    expires_at=(created + timedelta(days=30)) if created else None,
                    last_seen_at=created,
                )
            )

        for r in rows(source, "profiles"):
            profile = Profile(
                user_id=r["user_id"],
                display_name=r["display_name"] or "",
                dob=parse_date(r["dob"]),
                gender=r["gender"] or "",
                seek_gender=r["seek_gender"] or "",
                city=r["city"] or "",
                relationship_status=r["relationship_status"] or "PAUSED",
                eligibility_status=r["eligibility_status"] or "NOT_ACTIVE_FOR_MATCHING",
                dating_goal=r["dating_goal"] or "",
                readiness_chat=r["readiness_chat"] or "",
                readiness_offline=r["readiness_offline"] or "",
                readiness_score=r["readiness_score"] or 0,
                bio=r["bio"] or "",
                height=r["height"],
                smoking=r["smoking"] or "",
                alcohol=r["alcohol"] or "",
                lifestyle=r["lifestyle"] or "",
                religion=r["religion"] or "",
                nationality=r["nationality"] or "",
                children_attitude=r["children_attitude"] or "",
                children_plans=r["children_plans"] or "",
                questionnaire_completed=bool(r["questionnaire_completed"]),
                profile_completed=bool(r["profile_completed"]),
                status_confirmed_at=parse_dt(r["status_confirmed_at"]),
                updated_at=parse_dt(r["updated_at"]) or datetime.now().astimezone(),
            )
            session.add(profile)
            session.add(
                UserStatusHistory(
                    user_id=r["user_id"],
                    relationship_status=profile.relationship_status,
                    eligibility_status=profile.eligibility_status,
                    source="legacy-v7-import",
                    created_at=profile.updated_at,
                )
            )

        for r in rows(source, "criteria"):
            raw = json_value(r["data"], {})
            session.add(LegacyPartnerCriteria(user_id=r["user_id"], raw_json=raw))
            for key, spec in raw.items():
                if isinstance(spec, dict):
                    add_preference(session, r["user_id"], key, spec)

        qversion = QuestionnaireVersion(
            code=V7_VERSION_CODE,
            title=V7_VERSION_TITLE,
            is_active=True,
        )
        session.add(qversion)
        session.flush()

        qmap = {}
        for pos, (legacy_qid, category, question_text) in enumerate(V7_QUESTIONS, start=1):
            item = QuestionnaireQuestion(
                version_id=qversion.id,
                legacy_qid=legacy_qid,
                category=category,
                question_text=question_text,
                answer_type="scale",
                is_required=True,
                options_json=V7_SCALE_OPTIONS,
                weight=1,
                match_logic={"scale_min": 1, "scale_max": 5, "legacy_formula": "100-25*abs(a-b)"},
                position=pos,
            )
            session.add(item)
            session.flush()
            qmap[legacy_qid] = item.id

        for r in rows(source, "answers"):
            session.add(
                QuestionnaireAnswer(
                    user_id=r["user_id"],
                    question_id=qmap[r["qid"]],
                    value_int=r["value"],
                )
            )

        legacy_photo_blobs = []
        for r in rows(source, "photos"):
            session.add(
                Photo(
                    id=r["id"],
                    user_id=r["user_id"],
                    mime=r["mime"],
                    is_main=bool(r["is_main"]),
                    moderation_status=r["moderation_status"] or "PENDING",
                    created_at=parse_dt(r["created_at"]),
                )
            )
            legacy_photo_blobs.append((r["id"], r["data"]))
        session.flush()
        for photo_id, base64_data in legacy_photo_blobs:
            session.add(LegacyPhotoBlob(photo_id=photo_id, base64_data=base64_data))

        for r in rows(source, "likes"):
            session.add(
                Interest(
                    from_user=r["from_user"],
                    to_user=r["to_user"],
                    state="INTERESTED",
                    created_at=parse_dt(r["created_at"]),
                )
            )

        match_ids = []
        for r in rows(source, "matches"):
            user1, user2 = sorted((r["user1"], r["user2"]))
            session.add(
                Match(
                    id=r["id"],
                    user1=user1,
                    user2=user2,
                    compatibility_score=r["compatibility_score"],
                    mutual_fit_score=r["mutual_fit_score"],
                    algorithm_version="legacy-v7",
                    created_at=parse_dt(r["created_at"]),
                )
            )
            match_ids.append(r["id"])
        session.flush()

        conversation_by_match = {}
        for match_id in match_ids:
            conv = Conversation(match_id=match_id)
            session.add(conv)
            session.flush()
            conversation_by_match[match_id] = conv.id

        for r in rows(source, "messages"):
            session.add(
                Message(
                    id=r["id"],
                    conversation_id=conversation_by_match[r["match_id"]],
                    legacy_match_id=r["match_id"],
                    sender=r["sender"],
                    body=r["body"],
                    created_at=parse_dt(r["created_at"]),
                    read_at=parse_dt(r["read_at"]),
                )
            )

        for r in rows(source, "date_proposals"):
            session.add(
                DateProposal(
                    id=r["id"],
                    match_id=r["match_id"],
                    proposer=r["proposer"],
                    format=r["format"],
                    when_text=r["when_text"],
                    district=r["district"] or "",
                    budget=r["budget"] or "",
                    note=r["note"] or "",
                    status=r["status"] or "PENDING",
                    created_at=parse_dt(r["created_at"]),
                )
            )

        for r in rows(source, "blocks"):
            session.add(
                Block(
                    blocker=r["blocker"],
                    blocked=r["blocked"],
                    created_at=parse_dt(r["created_at"]),
                )
            )

        for r in rows(source, "reports"):
            session.add(
                Report(
                    id=r["id"],
                    reporter=r["reporter"],
                    target_user=r["target_user"],
                    photo_id=r["photo_id"],
                    reason=r["reason"],
                    status="OPEN",
                    created_at=parse_dt(r["created_at"]),
                )
            )

        for r in rows(source, "attribution"):
            session.add(
                MarketingAttribution(
                    user_id=r["user_id"],
                    utm_source=r["utm_source"] or "",
                    utm_medium=r["utm_medium"] or "",
                    utm_campaign=r["utm_campaign"] or "",
                    utm_content=r["utm_content"] or "",
                    utm_term=r["utm_term"] or "",
                    referral_input=r["referral_input"] or "",
                )
            )

        for r in rows(source, "notifications"):
            session.add(
                Notification(
                    id=r["id"],
                    user_id=r["user_id"],
                    kind=r["kind"],
                    text=r["text"],
                    created_at=parse_dt(r["created_at"]),
                    read_at=parse_dt(r["read_at"]),
                )
            )

        for r in rows(source, "settings"):
            session.add(Setting(key=r["key"], value=r["value"]))

        for r in rows(source, "events"):
            session.add(
                ProductEvent(
                    id=r["id"],
                    user_id=r["user_id"],
                    event_type=r["event_type"],
                    metadata_json=json_value(r["meta"], {}),
                    created_at=parse_dt(r["created_at"]),
                )
            )

        sync_sequences(session)
        session.commit()

    source.close()


def main():
    parser = argparse.ArgumentParser(description="Import MatchLab v7 SQLite data into an empty PostgreSQL schema.")
    parser.add_argument("sqlite_path")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    import_database(args.sqlite_path, args.database_url)
    print("IMPORT_OK")


if __name__ == "__main__":
    main()
