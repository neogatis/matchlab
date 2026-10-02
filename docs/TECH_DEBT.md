# MatchLab v7 technical debt register

## P0 — block real user acquisition

1. **Ephemeral persistence** — SQLite is stored on the application filesystem and the current Railway service has no attached volume.
2. **Source deployment through environment variables** — production source is encoded in Railway variables and reconstructed at startup; this has already produced fragile deployments.
3. **Photos stored inside SQLite as base64 text** — there is no object storage or image-processing pipeline.
4. **No schema migration system** — schema creation at application startup is the only schema management.
5. **Pre-launch enforcement gap** — candidate delivery is disabled correctly, but every interest/match mutation must enforce the same server-side feature gate.
6. **Moderation enforcement gap** — candidate display and profile completion must count only photos that are allowed by moderation policy.
7. **Admin authentication needs redesign** — move admin access away from shared URL parameters to proper authenticated admin sessions and RBAC.
8. **No rate limiting** — authentication and sensitive endpoints need abuse/brute-force controls.

## P1 — production correctness and security

- Sessions need explicit expiry, rotation, revocation and device/session management.
- Cookie policy, CSRF strategy and security headers need production hardening.
- Email verification, phone OTP, Google and Apple authentication are absent.
- Password policy and password hashing should move to a production identity layer using a modern configuration such as Argon2id.
- Input validation is incomplete.
- Uploaded images require real binary/image validation rather than trusting client metadata.
- Account deletion, data deletion/export, retention and consent workflows are absent.
- User-facing block/report coverage is incomplete.
- Relational constraints and supporting indexes need a production schema review.
- Logging/observability are insufficient.
- Launch-market configuration is hardcoded in parts of the legacy application.

## P1 — matching correctness

- Only required criteria currently enforce partner preferences; important/preference levels are not fully reflected in scoring.
- The target model is HARD / IMPORTANT / PREFERENCE / IGNORE.
- Mutual-fit scoring is still simpler than the target two-way preference engine.
- Missing target attributes can weaken some required filters.
- Candidate volume should remain intentionally small for the personal-matchmaker positioning.
- Matching results have no algorithm version.
- Questionnaire answers have no questionnaire version.

## P2 — product and engineering completeness

- OpenAI configuration exists in the runtime, but the recovered v7 source contains no actual OpenAI request for compatibility explanation.
- Frontend, admin UI, routing, persistence and business logic live in one legacy Python file.
- Production notification delivery is not implemented.
- Referral tracking is still basic.
- Analytics event coverage is incomplete relative to the product specification.
- Subscription/payment and app-store billing infrastructure are not implemented.
