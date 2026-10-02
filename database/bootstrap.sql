BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> de35f9d50310

CREATE TABLE audit_logs (
    id BIGSERIAL NOT NULL, 
    actor_type VARCHAR(40) NOT NULL, 
    actor_id VARCHAR(160), 
    action VARCHAR(120) NOT NULL, 
    target_type VARCHAR(80), 
    target_id VARCHAR(160), 
    metadata_json JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE moderation_actions (
    id BIGSERIAL NOT NULL, 
    actor VARCHAR(160) NOT NULL, 
    target_type VARCHAR(40) NOT NULL, 
    target_id VARCHAR(80) NOT NULL, 
    action VARCHAR(80) NOT NULL, 
    metadata_json JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE questionnaire_versions (
    id BIGSERIAL NOT NULL, 
    code VARCHAR(64) NOT NULL, 
    title VARCHAR(160) NOT NULL, 
    is_active BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE TABLE settings (
    key VARCHAR(120) NOT NULL, 
    value TEXT NOT NULL, 
    PRIMARY KEY (key)
);

CREATE TABLE users (
    id BIGSERIAL NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    password_hash TEXT NOT NULL, 
    referral_code VARCHAR(64) NOT NULL, 
    referred_by BIGINT, 
    invites_sent INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_users_invites_nonnegative CHECK (invites_sent >= 0), 
    FOREIGN KEY(referred_by) REFERENCES users (id) ON DELETE SET NULL, 
    UNIQUE (email), 
    UNIQUE (referral_code)
);

CREATE UNIQUE INDEX ix_users_email_lower ON users (lower(email));

CREATE TABLE blocks (
    blocker BIGINT NOT NULL, 
    blocked BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (blocker, blocked), 
    FOREIGN KEY(blocked) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(blocker) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE consents (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    consent_type VARCHAR(100) NOT NULL, 
    version VARCHAR(64) NOT NULL, 
    granted BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_consents_user_id ON consents (user_id);

CREATE TABLE data_requests (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    request_type VARCHAR(40) NOT NULL, 
    status VARCHAR(40) DEFAULT 'PENDING' NOT NULL, 
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_data_requests_user_id ON data_requests (user_id);

CREATE TABLE interests (
    from_user BIGINT NOT NULL, 
    to_user BIGINT NOT NULL, 
    state VARCHAR(24) DEFAULT 'INTERESTED' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (from_user, to_user), 
    FOREIGN KEY(from_user) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(to_user) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE legacy_partner_criteria (
    user_id BIGINT NOT NULL, 
    raw_json JSONB NOT NULL, 
    imported_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE marketing_attribution (
    user_id BIGINT NOT NULL, 
    utm_source VARCHAR(255) DEFAULT '' NOT NULL, 
    utm_medium VARCHAR(255) DEFAULT '' NOT NULL, 
    utm_campaign VARCHAR(255) DEFAULT '' NOT NULL, 
    utm_content VARCHAR(255) DEFAULT '' NOT NULL, 
    utm_term VARCHAR(255) DEFAULT '' NOT NULL, 
    referral_input VARCHAR(255) DEFAULT '' NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE matches (
    id BIGSERIAL NOT NULL, 
    user1 BIGINT NOT NULL, 
    user2 BIGINT NOT NULL, 
    compatibility_score INTEGER NOT NULL, 
    mutual_fit_score INTEGER NOT NULL, 
    algorithm_version VARCHAR(64) DEFAULT 'legacy-v7' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_matches_compatibility CHECK (compatibility_score BETWEEN 0 AND 100), 
    CONSTRAINT ck_matches_mutual_fit CHECK (mutual_fit_score BETWEEN 0 AND 100), 
    FOREIGN KEY(user1) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(user2) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_matches_pair UNIQUE (user1, user2)
);

CREATE INDEX ix_matches_user1_created ON matches (user1, created_at);

CREATE INDEX ix_matches_user2_created ON matches (user2, created_at);

CREATE TABLE notifications (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    kind VARCHAR(80) NOT NULL, 
    text TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    read_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE partner_preferences (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    criterion_key VARCHAR(80) NOT NULL, 
    importance VARCHAR(20) DEFAULT 'IGNORE' NOT NULL, 
    value_text TEXT, 
    value_bool BOOLEAN, 
    min_value NUMERIC(12, 3), 
    max_value NUMERIC(12, 3), 
    values_json JSONB, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_partner_preferences_importance CHECK (importance IN ('HARD','IMPORTANT','PREFERENCE','IGNORE')), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_partner_preferences_user_criterion UNIQUE (user_id, criterion_key)
);

CREATE INDEX ix_partner_preferences_user_id ON partner_preferences (user_id);

CREATE TABLE photos (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    storage_key TEXT, 
    mime VARCHAR(100) NOT NULL, 
    is_main BOOLEAN DEFAULT 'false' NOT NULL, 
    sort_order INTEGER DEFAULT '0' NOT NULL, 
    moderation_status VARCHAR(40) DEFAULT 'PENDING' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (storage_key)
);

CREATE INDEX ix_photos_user_id ON photos (user_id);

CREATE INDEX ix_photos_user_status ON photos (user_id, moderation_status);

CREATE TABLE product_events (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT, 
    event_type VARCHAR(100) NOT NULL, 
    metadata_json JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_product_events_event_type ON product_events (event_type);

CREATE INDEX ix_product_events_user_id ON product_events (user_id);

CREATE TABLE profiles (
    user_id BIGINT NOT NULL, 
    display_name VARCHAR(120) DEFAULT '' NOT NULL, 
    dob DATE, 
    gender VARCHAR(32) DEFAULT '' NOT NULL, 
    seek_gender VARCHAR(32) DEFAULT '' NOT NULL, 
    city VARCHAR(120) DEFAULT '' NOT NULL, 
    country_code VARCHAR(2) DEFAULT 'KZ' NOT NULL, 
    relationship_status VARCHAR(40) DEFAULT 'PAUSED' NOT NULL, 
    eligibility_status VARCHAR(40) DEFAULT 'NOT_ACTIVE_FOR_MATCHING' NOT NULL, 
    dating_goal VARCHAR(80) DEFAULT '' NOT NULL, 
    readiness_chat VARCHAR(40) DEFAULT '' NOT NULL, 
    readiness_offline VARCHAR(40) DEFAULT '' NOT NULL, 
    readiness_score INTEGER DEFAULT '0' NOT NULL, 
    bio TEXT DEFAULT '' NOT NULL, 
    height INTEGER, 
    smoking VARCHAR(40) DEFAULT '' NOT NULL, 
    alcohol VARCHAR(40) DEFAULT '' NOT NULL, 
    lifestyle VARCHAR(80) DEFAULT '' NOT NULL, 
    religion VARCHAR(120) DEFAULT '' NOT NULL, 
    nationality VARCHAR(120) DEFAULT '' NOT NULL, 
    children_attitude VARCHAR(80) DEFAULT '' NOT NULL, 
    children_plans VARCHAR(80) DEFAULT '' NOT NULL, 
    questionnaire_completed BOOLEAN DEFAULT 'false' NOT NULL, 
    profile_completed BOOLEAN DEFAULT 'false' NOT NULL, 
    status_confirmed_at TIMESTAMP WITH TIME ZONE, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id), 
    CONSTRAINT ck_profiles_height CHECK (height IS NULL OR height BETWEEN 100 AND 250), 
    CONSTRAINT ck_profiles_readiness_0_100 CHECK (readiness_score BETWEEN 0 AND 100), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_profiles_matchable ON profiles (eligibility_status, relationship_status, gender, seek_gender, city);

CREATE TABLE questionnaire_questions (
    id BIGSERIAL NOT NULL, 
    version_id BIGINT NOT NULL, 
    legacy_qid INTEGER, 
    category VARCHAR(120) NOT NULL, 
    question_text TEXT NOT NULL, 
    answer_type VARCHAR(40) DEFAULT 'scale' NOT NULL, 
    weight NUMERIC(8, 4) DEFAULT '1' NOT NULL, 
    match_logic JSONB DEFAULT '{}' NOT NULL, 
    position INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(version_id) REFERENCES questionnaire_versions (id) ON DELETE CASCADE, 
    CONSTRAINT uq_questions_version_legacy_qid UNIQUE (version_id, legacy_qid), 
    CONSTRAINT uq_questions_version_position UNIQUE (version_id, position)
);

CREATE TABLE sessions (
    token VARCHAR(255) NOT NULL, 
    user_id BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (token), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE user_status_history (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    relationship_status VARCHAR(40) NOT NULL, 
    eligibility_status VARCHAR(40) NOT NULL, 
    source VARCHAR(40) DEFAULT 'migration' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_user_status_history_user_id ON user_status_history (user_id);

CREATE TABLE conversations (
    id BIGSERIAL NOT NULL, 
    match_id BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE, 
    UNIQUE (match_id)
);

CREATE TABLE date_proposals (
    id BIGSERIAL NOT NULL, 
    match_id BIGINT NOT NULL, 
    proposer BIGINT NOT NULL, 
    format VARCHAR(80) NOT NULL, 
    when_text TEXT NOT NULL, 
    district VARCHAR(160) DEFAULT '' NOT NULL, 
    budget VARCHAR(120) DEFAULT '' NOT NULL, 
    note TEXT DEFAULT '' NOT NULL, 
    status VARCHAR(32) DEFAULT 'PENDING' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE, 
    FOREIGN KEY(proposer) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_date_proposals_match_id ON date_proposals (match_id);

CREATE TABLE legacy_photo_blobs (
    photo_id BIGINT NOT NULL, 
    base64_data TEXT NOT NULL, 
    imported_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (photo_id), 
    FOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE
);

CREATE TABLE match_score_components (
    match_id BIGINT NOT NULL, 
    component_key VARCHAR(80) NOT NULL, 
    score NUMERIC(8, 3) NOT NULL, 
    explanation_data JSONB DEFAULT '{}' NOT NULL, 
    PRIMARY KEY (match_id, component_key), 
    FOREIGN KEY(match_id) REFERENCES matches (id) ON DELETE CASCADE
);

CREATE TABLE questionnaire_answers (
    user_id BIGINT NOT NULL, 
    question_id BIGINT NOT NULL, 
    value_int INTEGER, 
    value_text TEXT, 
    value_json JSONB, 
    answered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (user_id, question_id), 
    FOREIGN KEY(question_id) REFERENCES questionnaire_questions (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE messages (
    id BIGSERIAL NOT NULL, 
    conversation_id BIGINT NOT NULL, 
    legacy_match_id BIGINT, 
    sender BIGINT NOT NULL, 
    body TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    read_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
    FOREIGN KEY(sender) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);

CREATE TABLE reports (
    id BIGSERIAL NOT NULL, 
    reporter BIGINT NOT NULL, 
    target_user BIGINT, 
    photo_id BIGINT, 
    message_id BIGINT, 
    reason VARCHAR(160) NOT NULL, 
    status VARCHAR(32) DEFAULT 'OPEN' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(message_id) REFERENCES messages (id) ON DELETE SET NULL, 
    FOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE SET NULL, 
    FOREIGN KEY(reporter) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(target_user) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_reports_reporter ON reports (reporter);

INSERT INTO alembic_version (version_num) VALUES ('de35f9d50310') RETURNING alembic_version.version_num;

-- Running upgrade de35f9d50310 -> fc57398b3a81

CREATE TABLE auth_outbox (
    id BIGSERIAL NOT NULL, 
    channel VARCHAR(20) NOT NULL, 
    recipient VARCHAR(320) NOT NULL, 
    template VARCHAR(80) NOT NULL, 
    payload_json JSONB DEFAULT '{}' NOT NULL, 
    status VARCHAR(24) DEFAULT 'PENDING' NOT NULL, 
    attempts INTEGER DEFAULT '0' NOT NULL, 
    available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    last_error TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_auth_outbox_pending ON auth_outbox (status, available_at);

CREATE TABLE auth_rate_limits (
    bucket_key VARCHAR(128) NOT NULL, 
    window_started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    hits INTEGER DEFAULT '0' NOT NULL, 
    blocked_until TIMESTAMP WITH TIME ZONE, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (bucket_key), 
    CONSTRAINT ck_auth_rate_limits_hits_nonnegative CHECK (hits >= 0)
);

CREATE TABLE auth_challenges (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT, 
    purpose VARCHAR(40) NOT NULL, 
    channel VARCHAR(20) NOT NULL, 
    target_hash VARCHAR(64) NOT NULL, 
    secret_hash VARCHAR(64) NOT NULL, 
    attempts INTEGER DEFAULT '0' NOT NULL, 
    max_attempts INTEGER DEFAULT '5' NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    consumed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_auth_challenges_attempts_nonnegative CHECK (attempts >= 0), 
    CONSTRAINT ck_auth_challenges_max_attempts CHECK (max_attempts BETWEEN 1 AND 20), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (secret_hash)
);

CREATE INDEX ix_auth_challenges_expires_at ON auth_challenges (expires_at);

CREATE INDEX ix_auth_challenges_target_hash ON auth_challenges (target_hash);

CREATE INDEX ix_auth_challenges_user_id ON auth_challenges (user_id);

CREATE TABLE auth_identities (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    provider VARCHAR(32) NOT NULL, 
    provider_subject VARCHAR(255) NOT NULL, 
    provider_email VARCHAR(320), 
    verified_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_auth_identity_provider_subject UNIQUE (provider, provider_subject)
);

CREATE INDEX ix_auth_identities_user_id ON auth_identities (user_id);

ALTER TABLE sessions ADD COLUMN secret_hash VARCHAR(64);

ALTER TABLE sessions ADD COLUMN last_seen_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE sessions ADD COLUMN user_agent_hash VARCHAR(64);

CREATE UNIQUE INDEX ix_sessions_secret_hash ON sessions (secret_hash);

ALTER TABLE users ADD COLUMN status VARCHAR(32) DEFAULT 'ACTIVE' NOT NULL;

ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE users ADD COLUMN phone_e164 VARCHAR(32);

ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE users ADD COLUMN password_updated_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE users ADD CONSTRAINT uq_users_phone_e164 UNIQUE (phone_e164);

UPDATE alembic_version SET version_num='fc57398b3a81' WHERE alembic_version.version_num = 'de35f9d50310';

COMMIT;

