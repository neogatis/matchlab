# Phase 24 — PostgreSQL HTTP cutover foundation

## DONE

A new production-oriented HTTP runtime now exists at `app/http/server.py`.

It is intentionally scoped to the **PRE-LAUNCH / WAITLIST acquisition flow**. Candidate output, interest actions, matching and chat are not exposed by this runtime while pre-launch is active.

## WHAT WAS BUILT

- PostgreSQL-only runtime; `DATABASE_URL` is mandatory.
- Fail-closed origin configuration via `PUBLIC_URL` / `ALLOWED_ORIGINS`.
- Secure session and CSRF cookies reuse the Phase 21 security policy.
- Request-body limits and JSON validation reuse Phase 21 controls.
- Banned/deletion-requested accounts are rejected at the HTTP boundary.
- Versioned `/api/v1` endpoints for:
  - email registration;
  - password login/logout;
  - basic 18+ profile;
  - relationship/open-to-dating status;
  - readiness;
  - questionnaire read/write;
  - partner preferences read/write;
  - waitlist status;
  - self compatibility profile.
- `/health` proves PostgreSQL connectivity and reports pre-launch feature flags.
- Contract tests for origin normalization and cookie parsing.

## SECURITY BEHAVIOR

State-changing authenticated requests require both:

1. an allowed `Origin`;
2. the double-submit CSRF token (`ml_csrf` cookie + `X-CSRF-Token` header).

Registration and login require an allowed Origin and issue both session and CSRF cookies.

The runtime never logs request bodies, credentials, cookies or authorization material.

## WHAT WAS TESTED

The Phase 24 workflow imports the production HTTP runtime with PostgreSQL/auth dependencies and runs the HTTP contract tests plus the Phase 21 security regressions.

## KNOWN ISSUES / RELEASE EVIDENCE STILL REQUIRED

This commit does **not** claim the public service is already cut over.

Before marking the App Store readiness blocker “PostgreSQL application connected to the public HTTP runtime” complete:

1. run all Alembic migrations on the production Neon branch;
2. ensure the active questionnaire and launch market are seeded;
3. configure `DATABASE_URL`, `PUBLIC_URL`, and optional `ALLOWED_ORIGINS`;
4. deploy the new image to the existing Railway service without changing its public URL;
5. verify `/health` against the public URL;
6. run registration -> profile -> questionnaire -> preferences -> waitlist smoke flow;
7. verify rollback to the previous image is available.

## NEXT PHASE

Phase 25 should add production photo object storage/upload HTTP endpoints. Completing photos is required before a waitlist profile can become fully ready.
