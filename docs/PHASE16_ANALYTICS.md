# Phase 16 — Product analytics

## Goal

Measure whether MatchLab moves users from registration to completed profiles, relevant mutual matches and real conversations. Profile views are not a success metric.

## Event taxonomy

Phase 16 defines product events for:

- REGISTRATION
- QUESTIONNAIRE_STARTED
- QUESTIONNAIRE_COMPLETED
- PHOTO_UPLOADED
- PROFILE_COMPLETED
- INTEREST_EXPRESSED
- MUTUAL_MATCH_CREATED
- CHAT_STARTED
- SUBSCRIPTION_STARTED

Existing operational events such as CANDIDATE_SKIPPED and MESSAGE_SENT remain valid.

Registration, questionnaire progression, photo upload, profile completion and first chat start are now instrumented in their domain services. Interest and mutual match events already existed.

## Metrics

The analytics service exposes:

- questionnaire_start_rate
- questionnaire_completion_rate
- profile_completion_rate
- match_rate
- mutual_interest_rate
- chat_start_rate
- D1 / D7 / D30
- report_rate
- USERS_WITH_RELEVANT_MATCH

USERS_WITH_RELEVANT_MATCH is defined as the number of unique users participating in at least one mutual MatchLab match.

D1/D7/D30 use a 24-hour activity window beginning exactly 1/7/30 days after registration. Only users old enough to have reached the window are included in the denominator.

## Metrics deliberately not invented

registration_conversion is returned as unavailable until the application records a real landing/install denominator.

subscription_conversion is returned as unavailable until Phase 18 introduces subscription architecture or actual subscription-start events.

Returning null with an explanation is preferred to presenting a fake conversion number.

## Profile completion

Phase 16 centralizes overall profile completion. A profile becomes complete only after:

- basic identity/profile fields are present;
- questionnaire is complete;
- partner preferences are complete;
- photos are complete.

The PROFILE_COMPLETED event is idempotent.

## Performance

Composite indexes are added for:

- product_events(user_id, created_at)
- product_events(event_type, created_at)

These support retention and funnel queries without changing event semantics.

## Admin console

The Phase 13 Analytics section now uses the Phase 16 product analytics service.
