from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    referral_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    referred_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    invites_sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ACTIVE")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_e164: Mapped[str | None] = mapped_column(String(32))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("invites_sent >= 0", name="ck_users_invites_nonnegative"),
        UniqueConstraint("phone_e164", name="uq_users_phone_e164"),
        Index("ix_users_email_lower", func.lower(email), unique=True),
    )


class Session(Base):
    __tablename__ = "sessions"

    # `token` is now a non-secret selector. The bearer secret is stored only as a hash.
    # It remains named `token` during the compatibility phase so Phase 2 imports stay readable.
    token: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    secret_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))


class AuthIdentity(Base):
    __tablename__ = "auth_identities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(320))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"),
    )


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_auth_challenges_attempts_nonnegative"),
        CheckConstraint("max_attempts BETWEEN 1 AND 20", name="ck_auth_challenges_max_attempts"),
    )


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    bucket_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("hits >= 0", name="ck_auth_rate_limits_hits_nonnegative"),
    )


class AuthOutbox(Base):
    __tablename__ = "auth_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    template: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_auth_outbox_pending", "status", "available_at"),
    )


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    city_code: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    default_language: Mapped[str] = mapped_column(String(16), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    supported_languages: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    registration_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    matching_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("country_code", "city_code", name="uq_markets_country_city"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_markets_latitude"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_markets_longitude"),
        Index("ix_markets_active", "registration_open", "matching_open"),
    )


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, server_default="")
    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    seek_gender: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    city: Mapped[str] = mapped_column(String(120), nullable=False, server_default="")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, server_default="KZ")
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id", name="fk_profiles_market_id", ondelete="SET NULL"), index=True)
    preferred_locale: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ru-KZ")
    relationship_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PAUSED")
    eligibility_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="NOT_ACTIVE_FOR_MATCHING")
    dating_goal: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    readiness_chat: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    readiness_offline: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bio: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    height: Mapped[int | None] = mapped_column(Integer)
    smoking: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    alcohol: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    lifestyle: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    religion: Mapped[str] = mapped_column(String(120), nullable=False, server_default="")
    nationality: Mapped[str] = mapped_column(String(120), nullable=False, server_default="")
    children_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    children_attitude: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    children_plans: Mapped[str] = mapped_column(String(80), nullable=False, server_default="")
    questionnaire_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    partner_preferences_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    photos_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    profile_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("readiness_score BETWEEN 0 AND 100", name="ck_profiles_readiness_0_100"),
        CheckConstraint("height IS NULL OR height BETWEEN 100 AND 250", name="ck_profiles_height"),
        CheckConstraint("relationship_status IN ('ACTIVE_SEARCH','OPEN_TO_MATCH','PAUSED','IN_RELATIONSHIP','NOT_ACTIVE')", name="ck_profiles_relationship_status"),
        CheckConstraint("eligibility_status IN ('ACTIVE_FOR_MATCHING','NOT_ACTIVE_FOR_MATCHING')", name="ck_profiles_eligibility_status"),
        CheckConstraint("children_status IN ('','NO_CHILDREN','HAS_CHILDREN')", name="ck_profiles_children_status"),
        Index("ix_profiles_matchable", "eligibility_status", "relationship_status", "gender", "seek_gender", "market_id"),
    )


class UserStatusHistory(Base):
    __tablename__ = "user_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_status: Mapped[str] = mapped_column(String(40), nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, server_default="migration")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class QuestionnaireVersion(Base):
    __tablename__ = "questionnaire_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class QuestionnaireQuestion(Base):
    __tablename__ = "questionnaire_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("questionnaire_versions.id", ondelete="CASCADE"), nullable=False)
    legacy_qid: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="scale")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    help_text: Mapped[str | None] = mapped_column(Text)
    options_json: Mapped[list | dict | None] = mapped_column(JSONB)
    weight: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, server_default="1")
    match_logic: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("version_id", "legacy_qid", name="uq_questions_version_legacy_qid"),
        UniqueConstraint("version_id", "position", name="uq_questions_version_position"),
        CheckConstraint("answer_type IN ('single','multiple','scale','priority','text')", name="ck_questions_answer_type"),
        CheckConstraint("weight > 0", name="ck_questions_positive_weight"),
    )


class QuestionnaireAnswer(Base):
    __tablename__ = "questionnaire_answers"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questionnaire_questions.id", ondelete="CASCADE"), primary_key=True)
    value_int: Mapped[int | None] = mapped_column(Integer)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[dict | None] = mapped_column(JSONB)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PartnerPreference(Base):
    __tablename__ = "partner_preferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    criterion_key: Mapped[str] = mapped_column(String(80), nullable=False)
    importance: Mapped[str] = mapped_column(String(20), nullable=False, server_default="IGNORE")
    value_text: Mapped[str | None] = mapped_column(Text)
    value_bool: Mapped[bool | None] = mapped_column(Boolean)
    min_value: Mapped[float | None] = mapped_column(Numeric(12, 3))
    max_value: Mapped[float | None] = mapped_column(Numeric(12, 3))
    values_json: Mapped[list | dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "criterion_key", name="uq_partner_preferences_user_criterion"),
        CheckConstraint("importance IN ('HARD','IMPORTANT','PREFERENCE','IGNORE')", name="ck_partner_preferences_importance"),
        CheckConstraint("min_value IS NULL OR max_value IS NULL OR min_value <= max_value", name="ck_partner_preferences_range_order"),
    )


class LegacyPartnerCriteria(Base):
    __tablename__ = "legacy_partner_criteria"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PhotoUploadTicket(Base):
    __tablename__ = "photo_upload_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PREPARED")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('PREPARED','CONSUMED','CANCELLED','EXPIRED')", name="ck_photo_upload_tickets_status"),
        Index("ix_photo_upload_tickets_user_status", "user_id", "status"),
    )


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str | None] = mapped_column(Text, unique=True)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    object_etag: Mapped[str | None] = mapped_column(String(160))
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    moderation_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PENDING")
    moderation_reason: Mapped[str | None] = mapped_column(String(255))
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_photos_user_status", "user_id", "moderation_status"),
        Index("uq_photos_one_main_per_user", "user_id", unique=True, postgresql_where=text("is_main")),
        CheckConstraint("moderation_status IN ('PENDING','APPROVED','REJECTED')", name="ck_photos_moderation_status"),
        CheckConstraint("byte_size IS NULL OR byte_size > 0", name="ck_photos_positive_size"),
        CheckConstraint("sort_order >= 0", name="ck_photos_sort_order_nonnegative"),
    )


class PhotoObjectDeletion(Base):
    __tablename__ = "photo_object_deletions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('PENDING','DONE','FAILED')", name="ck_photo_object_deletions_status"),
        CheckConstraint("attempts >= 0", name="ck_photo_object_deletions_attempts_nonnegative"),
        Index("ix_photo_object_deletions_status", "status", "created_at"),
    )


class LegacyPhotoBlob(Base):
    __tablename__ = "legacy_photo_blobs"

    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    base64_data: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Interest(Base):
    __tablename__ = "interests"

    from_user: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    to_user: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, server_default="INTERESTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user1: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user2: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    compatibility_score: Mapped[int] = mapped_column(Integer, nullable=False)
    mutual_fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="legacy-v7")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user1", "user2", name="uq_matches_pair"),
        CheckConstraint("compatibility_score BETWEEN 0 AND 100", name="ck_matches_compatibility"),
        CheckConstraint("mutual_fit_score BETWEEN 0 AND 100", name="ck_matches_mutual_fit"),
        Index("ix_matches_user1_created", "user1", "created_at"),
        Index("ix_matches_user2_created", "user2", "created_at"),
    )


class MatchScoreComponent(Base):
    __tablename__ = "match_score_components"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    component_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    score: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    explanation_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    legacy_match_id: Mapped[int | None] = mapped_column(BigInteger)
    sender: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DateProposal(Base):
    __tablename__ = "date_proposals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True)
    proposer: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format: Mapped[str] = mapped_column(String(80), nullable=False)
    when_text: Mapped[str] = mapped_column(Text, nullable=False)
    district: Mapped[str] = mapped_column(String(160), nullable=False, server_default="")
    budget: Mapped[str] = mapped_column(String(120), nullable=False, server_default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Block(Base):
    __tablename__ = "blocks"

    blocker: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    blocked: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reporter: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_user: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    photo_id: Mapped[int | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ModerationAction(Base):
    __tablename__ = "moderation_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MarketingAttribution(Base):
    __tablename__ = "marketing_attribution"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    utm_source: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    utm_medium: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    utm_campaign: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    utm_content: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    utm_term: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    referral_input: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductEvent(Base):
    __tablename__ = "product_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DataRequest(Base):
    __tablename__ = "data_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
