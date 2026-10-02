# Phase 5 — Questionnaire

## Goal

Turn the questionnaire into a versioned domain instead of keeping question content and completion logic inside the legacy monolith.

## Current v1 catalog

The exact 64-question MatchLab v7 questionnaire is preserved as version `v7-64`.

- 64 questions
- 16 sections
- 4 questions per section
- scale 1–5
- every v7 question is required
- original order and wording are preserved

## Schema

`questionnaire_versions`
- code
- title
- active flag

`questionnaire_questions`
- version
- legacy question id when applicable
- category
- text
- answer type
- required flag
- help text
- options JSON
- weight
- match logic
- position

`questionnaire_answers`
- user
- question
- integer/text/JSON typed answer storage

Supported answer types:
- single
- multiple
- scale
- priority
- text

## Service rules

- Only the active questionnaire accepts new answers.
- Scale values are validated against configured min/max.
- Single/multiple/priority answers are checked against configured options.
- Multiple answers reject duplicates.
- Optional text is capped at 2,000 characters.
- Progress is computed from required questions in the user's questionnaire version.
- `profiles.questionnaire_completed` becomes true only when every required question is answered.
- Seeding v7 is idempotent.

## Versioning

New questionnaire wording or scoring rules should create a new questionnaire version rather than silently changing the meaning of historical answers.

The matching engine will consume question version + weights + match logic in Phase 7.

## Legacy import

The SQLite-to-PostgreSQL importer no longer imports the old web application just to discover question content. It uses the versioned `catalog_v7` source of truth directly.

## Production activation

The current public v7 HTTP flow remains unchanged. After merge, the `v7-64` catalog can be seeded into Neon safely before the future PostgreSQL HTTP cutover.
