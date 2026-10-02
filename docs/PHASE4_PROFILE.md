# Phase 4 — User/profile model

## Goal

Move identity-independent user/profile rules out of the legacy monolith and make launch geography configurable rather than hardcoded.

## Added

- Configurable `markets` table.
- Market code, country, city, timezone, currency and supported languages.
- Independent registration and matching switches per market.
- Profile-to-market relation.
- Preferred locale on profiles.
- Explicit relationship-status and eligibility constraints.
- Service-level age validation.
- Centralized relationship/open-to-dating state transitions.
- Status history logging.
- Readiness formula preserved from v7.
- Centralized `is_matchable` eligibility check.

## Status model

Relationship status:
- ACTIVE_SEARCH
- OPEN_TO_MATCH
- PAUSED
- IN_RELATIONSHIP
- NOT_ACTIVE

Eligibility:
- ACTIVE_FOR_MATCHING
- NOT_ACTIVE_FOR_MATCHING

A profile is matchable only if:
- user is 18+;
- the market has matching enabled;
- relationship status is ACTIVE_SEARCH or OPEN_TO_MATCH;
- eligibility is ACTIVE_FOR_MATCHING;
- profile is completed;
- questionnaire is completed.

## Geography

Almaty remains the first launch market, but it is now data, not application logic.

Example market:
- code: KZ-ALA
- country: KZ
- city: ALA
- timezone: Asia/Almaty
- currency: KZT
- languages: ru-KZ / kk-KZ

Adding another city does not require code changes.

## Production status

The current public v7 application is unchanged. Phase 4 builds the normalized profile domain on PostgreSQL before HTTP cutover.
