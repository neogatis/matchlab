# Phase 21 — Security audit

## Scope reviewed

The PostgreSQL architecture was reviewed against the MatchLab requirements for:

- password hashing;
- session security;
- authentication challenges;
- rate limiting;
- authorization and RBAC;
- upload security;
- secret handling;
- audit logging;
- API protection;
- sensitive-data logging.

The frozen legacy v7 source remains a rollback baseline and is not treated as the target production architecture.

## Controls already present

- Argon2id password hashing.
- Transparent upgrade from the legacy PBKDF2 format after successful login.
- Selector + secret sessions: the bearer secret is stored only as a SHA-256 digest.
- Explicit expiry and revocation.
- Password reset revokes all sessions.
- Database-backed login rate limiting.
- One-time expiring verification/reset challenges with attempt limits.
- Admin console RBAC.
- Moderation and sensitive console mutations are audited.
- Photo uploads use short-lived presigned object-storage URLs and post-upload metadata validation.
- Push tokens are represented by hash + vault reference rather than raw token storage.
- Generic chat push/notification payloads do not include message bodies.
- Billing domain consumes transactions explicitly marked as verified instead of trusting client plan flags.

## Phase 21 additions

- Canonical secure session-cookie policy: Secure + HttpOnly + SameSite=Lax.
- Separate Secure SameSite=Strict CSRF cookie policy for a double-submit token.
- Constant-time CSRF equality check.
- Exact origin allow-list validation.
- JSON request size limit and strict UTF-8/JSON parsing primitive.
- Recursive sensitive-field redaction for structured logs.
- Static source scan for hardcoded secret-like assignments, query-string secrets and insecure session-cookie patterns.
- Security tests for cookie injection, CSRF mismatch, hostile origin suffixes, oversized/invalid JSON and log redaction.

## Remaining release blockers

The largest remaining security issue is architectural rather than a missing helper:

**the new PostgreSQL application still does not own the public HTTP runtime.**

Therefore the security primitives in this phase must be wired into the production HTTP layer during cutover. Until that happens, do not call the new stack internet-ready.

Before cutover, the HTTP application must enforce:

1. Secure/HttpOnly session cookies from this package.
2. CSRF validation on state-changing cookie-authenticated requests.
3. Origin allow-list checks.
4. Request body limits before JSON parsing/uploads.
5. Per-route authorization and console role checks.
6. Rate limiting for login, verification, password reset and abuse-sensitive actions.
7. Structured log redaction.
8. No admin secrets in query strings.
9. TLS-only public endpoints.
10. Provider webhook signature/receipt verification before calling billing verified-transaction services.

## Storage / secrets

Runtime credentials must stay in environment/secret managers and must never be committed.

Photo object storage credentials and push token vault/provider credentials are still deployment dependencies for the future production HTTP cutover.

## Data deletion

A deletion request currently deactivates the account. Retention-aware physical deletion/export still needs an explicit privacy-retention implementation before store release.

## Result

No hardcoded production credential was intentionally added by the PostgreSQL refactor.

Phase 21 establishes security controls and a CI gate, but the product remains **not ready for public cutover** until the new HTTP boundary applies them end-to-end.
