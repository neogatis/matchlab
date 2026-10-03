# Phase 22 — Performance audit

## Scope

The PostgreSQL path was reviewed for bounded work, index coverage, large candidate pools and known N+1 behavior.

## Good foundations

- Profiles have a composite matchability index.
- Partner preferences are indexed by user and unique by criterion.
- Questionnaire answers use a user/question composite primary key.
- Interests, messages, product events, reports and push outboxes have query-specific indexes.
- Candidate output remains deliberately small (default 5, maximum 20).
- Message history is cursor-paginated.
- Console/user lists are paginated or hard-limited.
- Worker-style photo/push deletion/delivery operations have bounded batches.

## Phase 22 hardening

Matching now validates the amount of candidate work requested:
- output limit: 1–20;
- candidate evaluation pool: at most 1,000 per request;
- default pool is 1,000.

A performance regression test counts SQL statements while ranking a synthetic candidate pool. This is intentionally a regression ceiling, not a claim that the query shape is optimal.

## Important finding

The current deterministic matching implementation still evaluates candidates one by one and performs repeated profile/preference/questionnaire/activity queries.

That is an **N+1 query pattern**.

It is acceptable for the current empty/pre-launch database and test pools, but it is not the desired architecture for a large public launch.

Before high-volume production, matching should move to a batch pipeline that preloads:
- candidate profiles/markets;
- partner preferences;
- questionnaire answer vectors;
- activity timestamps;
- block/interest/match exclusions;

then evaluates the shortlist in memory or via precomputed feature tables.

## Correctness over premature optimization

The audit does not replace the deterministic mutual matching rules with opaque vector/AI ranking just to reduce query count.

The Phase 7 matching logic remains the source of truth.

## Public cutover

Performance testing of real HTTP latency, concurrency, object storage and external push/billing providers cannot be considered complete until the PostgreSQL HTTP runtime exists.

Phase 22 therefore marks HTTP load testing as a cutover blocker rather than inventing latency numbers from unit tests.
