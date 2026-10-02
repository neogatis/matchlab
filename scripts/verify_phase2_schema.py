#!/usr/bin/env python3
from sqlalchemy import inspect, text
from app.db.session import make_engine

EXPECTED = {
    "users", "sessions", "profiles", "user_status_history",
    "questionnaire_versions", "questionnaire_questions", "questionnaire_answers",
    "partner_preferences", "legacy_partner_criteria",
    "photos", "legacy_photo_blobs", "interests", "matches",
    "match_score_components", "conversations", "messages", "date_proposals",
    "blocks", "reports", "moderation_actions", "marketing_attribution",
    "notifications", "product_events", "settings", "consents",
    "data_requests", "audit_logs",
}

engine = make_engine()
with engine.connect() as c:
    inspector = inspect(c)
    tables = set(inspector.get_table_names())
    missing = EXPECTED - tables
    extra = tables - EXPECTED - {"alembic_version"}
    assert not missing, f"missing tables: {sorted(missing)}"
    assert not extra, f"unexpected tables: {sorted(extra)}"
    assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert any(i["name"] == "ix_profiles_matchable" for i in inspector.get_indexes("profiles"))
    assert any(i["name"] == "ix_photos_user_status" for i in inspector.get_indexes("photos"))
    assert any(u["name"] == "uq_partner_preferences_user_criterion" for u in inspector.get_unique_constraints("partner_preferences"))
print("PHASE2_SCHEMA_OK")
