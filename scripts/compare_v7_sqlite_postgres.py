#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import make_engine


def norm(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dict, list)):
        return value
    return value


def sqlite_rows(c, sql, params=()):
    return [dict(r) for r in c.execute(sql, params).fetchall()]


def pg_rows(c, sql, params=None):
    return [dict(r._mapping) for r in c.execute(text(sql), params or {}).fetchall()]


def canonical(rows, fields):
    out = []
    for row in rows:
        item = {k: norm(row.get(k)) for k in fields}
        out.append(item)
    return out


def digest(items):
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def assert_equal(report, name, source, target):
    ok = source == target
    report["checks"][name] = {
        "ok": ok,
        "source_count": len(source) if isinstance(source, list) else None,
        "target_count": len(target) if isinstance(target, list) else None,
        "source_sha256": digest(source) if isinstance(source, list) else None,
        "target_sha256": digest(target) if isinstance(target, list) else None,
    }
    if not ok:
        report["ok"] = False
        report["checks"][name]["source_sample"] = source[:3] if isinstance(source, list) else source
        report["checks"][name]["target_sample"] = target[:3] if isinstance(target, list) else target


def compare_database(sqlite_path: str, postgres_url: str):
    sc = sqlite3.connect(sqlite_path)
    sc.row_factory = sqlite3.Row
    engine = make_engine(postgres_url)
    report = {"ok": True, "checks": {}}

    with engine.connect() as pc:
        assert_equal(
            report,
            "users",
            canonical(
                sqlite_rows(sc, "SELECT id,email,password_hash,referral_code,referred_by,invites_sent,created_at FROM users ORDER BY id"),
                ["id","email","password_hash","referral_code","referred_by","invites_sent","created_at"],
            ),
            canonical(
                pg_rows(pc, "SELECT id,email,password_hash,referral_code,referred_by,invites_sent,created_at FROM users ORDER BY id"),
                ["id","email","password_hash","referral_code","referred_by","invites_sent","created_at"],
            ),
        )

        source_sessions = []
        for r in sqlite_rows(sc, "SELECT token,user_id,created_at FROM sessions ORDER BY token"):
            h = hashlib.sha256(r["token"].encode("utf-8")).hexdigest()
            source_sessions.append({
                "selector": "legacy:" + h[:32],
                "secret_hash": h,
                "user_id": r["user_id"],
                "created_at": norm(datetime.fromisoformat(r["created_at"].replace("Z","+00:00"))) if r["created_at"] else None,
            })
        target_sessions = canonical(
            pg_rows(pc, "SELECT token AS selector,secret_hash,user_id,created_at FROM sessions ORDER BY token"),
            ["selector","secret_hash","user_id","created_at"],
        )
        assert_equal(report, "sessions_hashed", source_sessions, target_sessions)

        profile_fields = [
            "user_id","display_name","dob","gender","seek_gender","city","relationship_status",
            "eligibility_status","dating_goal","readiness_chat","readiness_offline","readiness_score",
            "bio","height","smoking","alcohol","lifestyle","religion","nationality","children_attitude",
            "children_plans","questionnaire_completed","profile_completed","status_confirmed_at","updated_at",
        ]
        source_profiles = canonical(
            sqlite_rows(sc, "SELECT * FROM profiles ORDER BY user_id"),
            profile_fields,
        )
        for row in source_profiles:
            row["questionnaire_completed"] = bool(row["questionnaire_completed"])
            row["profile_completed"] = bool(row["profile_completed"])
        target_profiles = canonical(
            pg_rows(pc, "SELECT " + ",".join(profile_fields) + " FROM profiles ORDER BY user_id"),
            profile_fields,
        )
        assert_equal(report, "profiles", source_profiles, target_profiles)

        source_criteria = []
        for r in sqlite_rows(sc, "SELECT user_id,data FROM criteria ORDER BY user_id"):
            source_criteria.append({"user_id": r["user_id"], "raw_json": json.loads(r["data"] or "{}")})
        target_criteria = canonical(
            pg_rows(pc, "SELECT user_id,raw_json FROM legacy_partner_criteria ORDER BY user_id"),
            ["user_id","raw_json"],
        )
        assert_equal(report, "criteria_legacy_json", source_criteria, target_criteria)

        source_answers = canonical(
            sqlite_rows(sc, "SELECT user_id,qid,value FROM answers ORDER BY user_id,qid"),
            ["user_id","qid","value"],
        )
        target_answers = canonical(
            pg_rows(
                pc,
                """
                SELECT a.user_id, q.legacy_qid AS qid, a.value_int AS value
                FROM questionnaire_answers a
                JOIN questionnaire_questions q ON q.id=a.question_id
                ORDER BY a.user_id,q.legacy_qid
                """,
            ),
            ["user_id","qid","value"],
        )
        assert_equal(report, "answers", source_answers, target_answers)

        source_photos = canonical(
            sqlite_rows(sc, "SELECT id,user_id,mime,is_main,moderation_status,created_at FROM photos ORDER BY id"),
            ["id","user_id","mime","is_main","moderation_status","created_at"],
        )
        for row in source_photos:
            row["is_main"] = bool(row["is_main"])
        target_photos = canonical(
            pg_rows(pc, "SELECT id,user_id,mime,is_main,moderation_status,created_at FROM photos ORDER BY id"),
            ["id","user_id","mime","is_main","moderation_status","created_at"],
        )
        assert_equal(report, "photos_metadata", source_photos, target_photos)

        source_blobs = []
        for r in sqlite_rows(sc, "SELECT id,data FROM photos ORDER BY id"):
            raw = (r["data"] or "").encode()
            source_blobs.append({"photo_id": r["id"], "length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        target_blobs = []
        for r in pg_rows(pc, "SELECT photo_id,base64_data FROM legacy_photo_blobs ORDER BY photo_id"):
            raw = (r["base64_data"] or "").encode()
            target_blobs.append({"photo_id": r["photo_id"], "length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        assert_equal(report, "photo_blobs", source_blobs, target_blobs)

        assert_equal(
            report,
            "interests",
            canonical(sqlite_rows(sc, "SELECT from_user,to_user,created_at FROM likes ORDER BY from_user,to_user"), ["from_user","to_user","created_at"]),
            canonical(pg_rows(pc, "SELECT from_user,to_user,created_at FROM interests ORDER BY from_user,to_user"), ["from_user","to_user","created_at"]),
        )

        assert_equal(
            report,
            "matches",
            canonical(sqlite_rows(sc, "SELECT id,user1,user2,compatibility_score,mutual_fit_score,created_at FROM matches ORDER BY id"), ["id","user1","user2","compatibility_score","mutual_fit_score","created_at"]),
            canonical(pg_rows(pc, "SELECT id,user1,user2,compatibility_score,mutual_fit_score,created_at FROM matches ORDER BY id"), ["id","user1","user2","compatibility_score","mutual_fit_score","created_at"]),
        )

        assert_equal(
            report,
            "messages",
            canonical(sqlite_rows(sc, "SELECT id,match_id,sender,body,created_at,read_at FROM messages ORDER BY id"), ["id","match_id","sender","body","created_at","read_at"]),
            canonical(pg_rows(pc, "SELECT id,legacy_match_id AS match_id,sender,body,created_at,read_at FROM messages ORDER BY id"), ["id","match_id","sender","body","created_at","read_at"]),
        )

        date_fields = ["id","match_id","proposer","format","when_text","district","budget","note","status","created_at"]
        assert_equal(
            report,
            "date_proposals",
            canonical(sqlite_rows(sc, "SELECT * FROM date_proposals ORDER BY id"), date_fields),
            canonical(pg_rows(pc, "SELECT " + ",".join(date_fields) + " FROM date_proposals ORDER BY id"), date_fields),
        )

        assert_equal(
            report,
            "blocks",
            canonical(sqlite_rows(sc, "SELECT blocker,blocked,created_at FROM blocks ORDER BY blocker,blocked"), ["blocker","blocked","created_at"]),
            canonical(pg_rows(pc, "SELECT blocker,blocked,created_at FROM blocks ORDER BY blocker,blocked"), ["blocker","blocked","created_at"]),
        )

        report_fields = ["id","reporter","target_user","photo_id","reason","created_at"]
        assert_equal(
            report,
            "reports",
            canonical(sqlite_rows(sc, "SELECT * FROM reports ORDER BY id"), report_fields),
            canonical(pg_rows(pc, "SELECT " + ",".join(report_fields) + " FROM reports ORDER BY id"), report_fields),
        )

        attr_fields = ["user_id","utm_source","utm_medium","utm_campaign","utm_content","utm_term","referral_input"]
        assert_equal(
            report,
            "marketing_attribution",
            canonical(sqlite_rows(sc, "SELECT * FROM attribution ORDER BY user_id"), attr_fields),
            canonical(pg_rows(pc, "SELECT " + ",".join(attr_fields) + " FROM marketing_attribution ORDER BY user_id"), attr_fields),
        )

        notification_fields = ["id","user_id","kind","text","created_at","read_at"]
        assert_equal(
            report,
            "notifications",
            canonical(sqlite_rows(sc, "SELECT * FROM notifications ORDER BY id"), notification_fields),
            canonical(pg_rows(pc, "SELECT " + ",".join(notification_fields) + " FROM notifications ORDER BY id"), notification_fields),
        )

        assert_equal(
            report,
            "settings",
            canonical(sqlite_rows(sc, "SELECT key,value FROM settings ORDER BY key"), ["key","value"]),
            canonical(pg_rows(pc, "SELECT key,value FROM settings ORDER BY key"), ["key","value"]),
        )

        source_events = []
        for r in sqlite_rows(sc, "SELECT id,user_id,event_type,meta,created_at FROM events ORDER BY id"):
            source_events.append({
                "id": r["id"],
                "user_id": r["user_id"],
                "event_type": r["event_type"],
                "metadata_json": json.loads(r["meta"] or "{}"),
                "created_at": norm(datetime.fromisoformat(r["created_at"].replace("Z","+00:00"))) if r["created_at"] else None,
            })
        target_events = canonical(
            pg_rows(pc, "SELECT id,user_id,event_type,metadata_json,created_at FROM product_events ORDER BY id"),
            ["id","user_id","event_type","metadata_json","created_at"],
        )
        assert_equal(report, "product_events", source_events, target_events)

        qcount = pc.execute(text("SELECT count(*) FROM questionnaire_questions WHERE legacy_qid IS NOT NULL")).scalar_one()
        report["checks"]["questionnaire_v7_64"] = {"ok": qcount == 64, "target_count": qcount}
        if qcount != 64:
            report["ok"] = False

        pref_count = pc.execute(text("SELECT count(*) FROM partner_preferences")).scalar_one()
        criterion_entries = 0
        for r in sqlite_rows(sc, "SELECT data FROM criteria"):
            raw = json.loads(r["data"] or "{}")
            criterion_entries += sum(1 for v in raw.values() if isinstance(v, dict))
        report["checks"]["normalized_preferences"] = {
            "ok": pref_count == criterion_entries,
            "source_count": criterion_entries,
            "target_count": pref_count,
        }
        if pref_count != criterion_entries:
            report["ok"] = False

    sc.close()
    return report


def main():
    p = argparse.ArgumentParser(description="Compare MatchLab v7 SQLite data with its PostgreSQL import.")
    p.add_argument("sqlite_path")
    p.add_argument("--database-url", default="")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    url = args.database_url or __import__("os").environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    report = compare_database(args.sqlite_path, url)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for name, result in report["checks"].items():
            print(("OK" if result["ok"] else "FAIL"), name)
        print("CUTOVER_VERIFY_OK" if report["ok"] else "CUTOVER_VERIFY_FAILED")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
