# Phase 6 — Partner preferences

## Goal

Represent partner criteria as explicit, private, typed preferences with the product's four importance levels:

- HARD
- IMPORTANT
- PREFERENCE
- IGNORE

Phase 6 stores and validates preferences. It does **not** decide matches yet; mutual filtering/scoring is Phase 7.

## Core criteria

The profile flow requires the user to explicitly configure:

- age
- gender
- market/city
- distance
- dating goal
- children status
- plans for children
- smoking
- alcohol
- lifestyle
- height

Optional:
- religion
- nationality

An optional criterion may simply remain absent. A core criterion can be explicitly set to IGNORE, which means “do not use this criterion”.

## Storage

Each criterion is one row in `partner_preferences`.

Depending on the criterion it uses:
- min/max numeric bounds;
- JSON list of allowed values;
- scalar text/bool fields where appropriate.

The service clears old values when importance becomes IGNORE, so stale constraints cannot accidentally affect matching.

## Validation

- age: 18–100
- height: 100–250 cm
- distance: 1–1000 km
- enum criteria accept only configured values
- ANY cannot be combined with specific options
- market codes must exist and be open for registration
- list values are deduplicated
- database enforces min <= max
- unknown criteria are rejected

## Privacy

Partner criteria are internal matching inputs. No public-profile helper is added in this phase.

Religion/nationality are optional. Nationality is treated only as user-provided text; it must never be inferred from name, face, photos or other proxies.

## Completion

`profiles.partner_preferences_completed` becomes true only after every core criterion has an explicit configuration, including explicit IGNORE selections.

## Legacy migration

Legacy v7 criteria are preserved losslessly in `legacy_partner_criteria` and normalized where possible. Migrated users can be asked to review/reconfirm the new Phase 6 criteria before becoming fully matchable.
