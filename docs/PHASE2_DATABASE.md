# Phase 2 — PostgreSQL database architecture

## Goal

Replace the ephemeral SQLite persistence layer with a migration-managed PostgreSQL foundation without losing current v7 data or changing user-visible behavior yet.

## Decisions

- PostgreSQL 16 is the target relational database.
- SQLAlchemy 2 defines the domain schema.
- Alembic owns all schema migrations.
- Existing v7 identifiers are preserved during import so references remain stable.
- Current base64 photo payloads are preserved temporarily in `legacy_photo_blobs` so migration is lossless. Phase 9 will move approved image bytes to object storage and remove this bridge.
- Current partner-criteria JSON is preserved in `legacy_partner_criteria`, while common criteria are also normalized into one-row-per-criterion `partner_preferences`. Phase 6 will finalize preference semantics.
- The 64-question v7 questionnaire becomes explicit version `v7-64`, so future questionnaire changes do not reinterpret historical answers.
- Matches receive `algorithm_version='legacy-v7'` during import.
- Existing match messages are migrated into one conversation per match.
- Sessions are preserved for migration compatibility only. Phase 3 will redesign production session security and expiration.

## Main tables

Identity and profile:
- users
- sessions
- profiles
- user_status_history

Questionnaire and preferences:
- questionnaire_versions
- questionnaire_questions
- questionnaire_answers
- partner_preferences
- legacy_partner_criteria

Media:
- photos
- legacy_photo_blobs

Matching and communication:
- interests
- matches
- match_score_components
- conversations
- messages
- date_proposals

Trust and safety:
- blocks
- reports
- moderation_actions

Growth and operations:
- marketing_attribution
- product_events
- notifications
- settings

Privacy foundation:
- consents
- data_requests
- audit_logs

## Migration strategy

1. Create an empty PostgreSQL database.
2. Run `alembic upgrade head`.
3. Put the legacy app into a short write freeze for final cutover.
4. Run `scripts/import_v7_sqlite_to_postgres.py` against the current SQLite file.
5. Verify row counts, questionnaire mapping, photos, criteria, matches/messages and attribution.
6. Start the PostgreSQL-aware application.
7. Keep the original SQLite file as a rollback snapshot until post-cutover verification is complete.

The importer refuses to write into a PostgreSQL database that already contains users, preventing accidental duplicate migration.

## Validation in CI

Every Phase 2 change runs against a real PostgreSQL 16 service container:

- generate/apply the initial Alembic migration;
- verify expected tables, indexes and constraints;
- create a representative v7 SQLite database;
- import it into PostgreSQL;
- verify normalized + legacy-preserved data;
- run `alembic check` to detect model/schema drift.

## Production cutover status

Not performed yet. The current Railway project cannot provision another service because the Railway account reports a resource-provision limit. Production therefore remains on the verified v7 SQLite baseline until a persistent PostgreSQL endpoint is available.
