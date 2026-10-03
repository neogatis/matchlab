# Phase 23 — App Store / Play Store readiness

## Result

MatchLab is **not ready for App Store or Google Play submission yet**.

That is an evidence-based result. The repository now has a fail-closed readiness gate so the project cannot be described as store-ready merely because backend domain code exists.

## Already built

The product architecture contains major release foundations:

- 18+ age gate;
- block and report domain flows;
- moderation queue and admin actions;
- photo moderation;
- account-deletion request state;
- privacy-preserving chat notifications;
- subscription/payment/entitlement data model;
- push outbox architecture;
- deterministic matching;
- pre-launch mode;
- RBAC operations console;
- security audit controls;
- full QA gate.

## Release blockers

The readiness gate currently marks these as incomplete:

1. PostgreSQL application connected to the public HTTP runtime.
2. Phase 21 security controls enforced end-to-end on that HTTP runtime.
3. Published Privacy Policy URL.
4. Published Terms of Use URL.
5. Complete self-service account deletion, including retention-aware execution.
6. User data export flow.
7. Explicit retention policy and purge rules.
8. Production object storage for photos.
9. Real APNS/FCM delivery credentials and provider clients.
10. Production purchase/subscription verification with store providers.
11. Sign in with Apple production flow.
12. Google Sign-In production flow.
13. Reproducible signed iOS release build.
14. Reproducible signed Android release build.
15. Store listing assets/metadata.
16. Review/test account and reviewer instructions.

## Mobile client

There is currently no verified native iOS/Android release project in this repository.

Creating a cosmetic mobile wrapper before the PostgreSQL HTTP cutover would duplicate risk. The stronger sequence is:

1. finish the production HTTP cutover;
2. complete privacy/delete/export;
3. connect storage/push/billing/auth providers;
4. build the mobile client against the stable API;
5. run device/store QA;
6. prepare listings and submit.

## Store-facing behavior

The mobile client must preserve the product concept:

- no endless swipe feed;
- explicit “Интересен человек” / “Пока пропустить” actions;
- chat only after mutual interest;
- block/report available from relevant user/chat/photo surfaces;
- status changes remove ineligible profiles from matching;
- compatibility wording must not promise relationship outcomes.

## Submission package

Before submission prepare:

- app name/subtitle/description;
- support URL;
- Privacy Policy URL;
- Terms URL;
- screenshots for supported device classes;
- app icon;
- age/content declarations;
- data collection/privacy disclosures based on actual production behavior;
- review credentials/instructions;
- account deletion instructions;
- subscription product mapping and reviewer notes if paid products are enabled.

Exact store forms and policy wording should be rechecked against current Apple/Google requirements at submission time because store requirements change.

## Gate

The current readiness service returns only evidence-backed completed capabilities.

It is deliberately fail-closed: a missing capability remains a blocker until there is implementation and release evidence.
