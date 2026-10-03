# MatchLab production roadmap

The implementation follows the product specification phase order and avoids a big-bang rewrite.

1. **Phase 1 — Architecture audit**: freeze exact baseline, source map, debt register, reproducible tests, move source deployment to Git.
2. **Phase 2 — Database architecture**: PostgreSQL schema, keys/indexes, Alembic migrations, SQLite import rehearsal and rollback plan.
3. **Phase 3 — Authentication**: verified email/phone identity, secure sessions, rate limiting, Google/Apple adapters.
4. **Phase 4 — User/profile model**: normalized profile/status/location/privacy model.
5. **Phase 5 — Questionnaire**: versioned questions/options/answers; preserve the current 64-question content as v1.
6. **Phase 6 — Partner preferences**: HARD / IMPORTANT / PREFERENCE / IGNORE normalized rules.
7. **Phase 7 — Matching engine**: one deterministic/versioned mutual matching service with exhaustive synthetic tests.
8. **Phase 8 — Compatibility results**: category scores and explanation contract; AI only for explanation.
9. **Phase 9 — Photos**: object storage, signed uploads, image validation, derivatives, EXIF removal and moderation.
10. **Phase 10 — Interest + mutual matching**.
11. **Phase 11 — Chat**.
12. **Phase 12 — Safety / block / reports**.
13. **Phase 13 — Admin panel with RBAC**.
14. **Phase 14 — Audience balance / supply-demand model**.
15. **Phase 15 — Pre-launch / waitlist on the production foundation**.
16. **Phase 16 — Analytics and retention**.
17. **Phase 17 — Referral system**.
18. **Phase 18 — Monetization infrastructure**.
19. **Phase 19 — Notifications**.
20. **Phase 20 — Full QA**.
21. **Phase 21 — Security audit**.
22. **Phase 22 — Performance audit**.
23. **Phase 23 — App Store / Play Store readiness**.

## Immediate dependency chain

```text
Git source deployment
  -> PostgreSQL + migrations
      -> production auth
          -> normalized profile/questionnaire/preferences
              -> versioned matching engine
                  -> object storage/photos
                      -> safe public pre-launch acquisition
```


## Post-roadmap release execution

24. **Phase 24 — PostgreSQL HTTP cutover**: versioned production HTTP runtime for pre-launch registration/profile/questionnaire/preferences.
25. **Phase 25 — Production photo storage**: private signed uploads, image sanitation/EXIF removal, photo HTTP APIs and moderator review.

Next: production deployment evidence, deletion worker, privacy/delete/export, then native client work.

26. **Phase 26 — Privacy / deletion / export / retention**: self-service export and deletion, external web deletion path, pseudonymous purge, legal pages and enforced cleanup windows.

Next: production cutover evidence and scheduled workers; then provider auth/push/billing and native clients.

27. **Phase 27 — Phone OTP + Google + Apple auth**: multichannel authentication and account linking with one-time OIDC nonce protection.

Next: production provider credentials, push delivery, billing provider verification, then native clients.
