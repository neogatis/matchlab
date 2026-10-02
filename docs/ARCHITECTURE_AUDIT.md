# MatchLab v7 architecture audit

## Scope
Audit of the exact production baseline `app/legacy/matchlab_v7.py` recovered from Railway. The file is 82,720 bytes and has SHA-256 `c133d8944158e42dcff32feb9ea9fa43e77cacb6582fe61cd618c8bd2eb1544d`.

## Current runtime architecture

```text
Browser
  -> Railway service `rin` (Python 3.12)
       -> ThreadingHTTPServer / BaseHTTPRequestHandler
       -> embedded HTML/CSS/JavaScript user UI
       -> embedded admin UI
       -> business logic + matching
       -> SQLite file under MATCH_DATA_DIR
       -> photos stored as base64 TEXT in SQLite
```

Production currently reconstructs the application source from Railway environment-variable chunks at container startup. No persistent Railway volume is attached to the service.

## Implemented behavior found in source

- Email/password registration and login.
- Mandatory DOB and 18+ rejection.
- Relationship/open-to-dating onboarding status.
- Almaty launch eligibility gate.
- Dating goal and readiness score.
- 64 unique Likert questionnaire items in 16 sections.
- Partner criteria stored by age, city, goal, children, smoking, alcohol, lifestyle, religion, nationality and height.
- Mutual hard-filter check, including gender direction and blocks table.
- Questionnaire-based compatibility + goal factor + readiness factor.
- PRE_LAUNCH_MODE and PRELAUNCH_MATCHING_ENABLED settings.
- Minimum two photos / maximum six.
- Waitlist screen when pre-launch matching is disabled.
- Interest, reciprocal match creation, text chat, unread counts and date proposals.
- UTM attribution and referral codes.
- Periodic 30-day dating-status confirmation.
- Admin dashboard with top-level audience metrics, age/city distributions, rudimentary supply-demand gaps and photo moderation.

## HTTP surface

Public pages: `/`, `/admin`, `/health`.

API includes registration/login/logout, profile, criteria, answers, photos, summary, feed, matches/chat, interest, date proposals, referral, photo reports, status and admin dashboard/settings/photo moderation.

## Data model

The baseline creates 15 SQLite tables at startup: `users`, `sessions`, `profiles`, `criteria`, `answers`, `photos`, `likes`, `matches`, `messages`, `date_proposals`, `blocks`, `reports`, `attribution`, `notifications`, `settings`, `events`.

There is no migration history. Partner criteria and event metadata are JSON strings. Photos are base64 strings in the database. Tables do not declare relational foreign keys.

## Authentication/security observations

- Passwords use PBKDF2-HMAC-SHA256 with a 16-byte random salt and 180,000 iterations.
- Session IDs use `secrets.token_urlsafe(32)` and are placed in HttpOnly, SameSite=Lax cookies.
- Session cookie is not marked Secure and server-side sessions do not have expiry/revocation metadata beyond creation time.
- No rate limiting is present.
- Admin authentication is a shared secret passed as a query parameter.
- No contact verification, Google/Apple Sign In, RBAC, audit log, deletion/export flow or consent ledger is present.

## Matching observations

`hard_pass(a,b)` correctly performs the required check in both directions and excludes paused/in-relationship/not-active/incomplete/blocked users. However, only `REQUIRED` criteria affect matching. `IMPORTANT` has no score contribution.

`compatibility(a,b)` averages answer distance, applies a dating-goal factor, then scales by the lower readiness score. This is deterministic and explainable, but it is much simpler than the target mutual-preference engine and has no algorithm versioning.

## Pre-launch observations

The feed correctly returns zero candidates while PRE_LAUNCH_MODE is true and PRELAUNCH_MATCHING_ENABLED is false. However, the like endpoint does not enforce the same flag, so matching can be bypassed through direct API calls if a target id is known.

## Photos/moderation observations

Photos are inserted as client-provided MIME + base64 text with only a string-length limit. There is no binary signature/image decoding validation, resize pipeline or EXIF stripping. Candidate profile display does not filter to approved photos, and completion counts all photos regardless of moderation status.

## Architecture conclusion

The baseline is a useful product prototype and contains meaningful business logic that should be preserved. It should not be expanded further in the current single-file/environment-variable deployment. The next architecture step is source-control deployment followed by PostgreSQL + migrations, while retaining the legacy implementation as a behavioral reference.
