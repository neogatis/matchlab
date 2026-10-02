# Phase 13 — Admin panel / operations console

## Goal

Provide a production-oriented MatchLab operations console with role-based access and without exposing authentication secrets or raw private chat bodies.

## Sections

The console contains the product-required sections:

- Dashboard
- Users
- Profiles
- Photos
- Reports
- Matches
- Chats metadata
- Questionnaire
- Matching settings
- Marketing
- Analytics
- Audience balance

## Access model

Console access is attached to a normal MatchLab user account through `admin_accounts`.

Roles:
- VIEWER
- MODERATOR
- ADMIN
- SUPERADMIN

The account must also be active.

The first SUPERADMIN can be bootstrapped only while the admin_accounts table is empty. Further role changes require SUPERADMIN.

## Privacy

User listings do not return password hashes or session secrets.

The Chats metadata section returns:
- conversation id;
- match id;
- created time;
- message count;
- last-message timestamp.

It deliberately does not return message bodies.

## Mutations

ADMIN can update matching/system settings through the audited setting mutation.

SUPERADMIN can change console roles. These changes are stored in audit_logs.

Moderation actions themselves remain in the Phase 12 safety service.

## UI

`render_console_page` provides the warm/dark MatchLab console view with responsive navigation and generic rendering of metric cards and tables.

The new panel is not wired into the legacy SQLite HTTP server. It belongs to the PostgreSQL application path so business logic is not duplicated into the legacy monolith.

## Audience balance

Phase 13 exposes basic audience counts, age distribution, cities and relationship statuses. Phase 14 adds the dedicated supply-vs-demand deficit engine and marketing recommendations.
