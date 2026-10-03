# Политика конфиденциальности MatchLab

Canonical public copy is generated from `app/privacy/legal.py`.

This repository copy documents the implemented behavior:

- 18+ only;
- account/profile/questionnaire/preferences/photo/chat/safety/payment data categories;
- private photo storage with EXIF/GPS stripping;
- self-service export;
- in-app and web account-deletion initiation;
- immediate account deactivation after deletion request;
- primary privacy purge within 30 days;
- limited pseudonymous retention for billing/security/legal obligations;
- retention cleanup windows enforced by `app/privacy/service.py`.

The public URL remains a release-evidence blocker until the production HTTP runtime is deployed.
