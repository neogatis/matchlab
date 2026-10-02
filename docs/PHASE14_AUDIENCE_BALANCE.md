# Phase 14 — Audience balance

## Goal

Turn audience balance into a deterministic operational tool for launch planning and acquisition.

## Overview

The balance report can be filtered by market code and shows:

- active matchable users;
- women / men / other;
- age distribution;
- cities;
- completed / incomplete profiles;
- active search;
- open to match;
- paused;
- in relationship.

Pre-launch markets are still counted as supply if profiles are otherwise ready. This lets the team build a balanced waitlist before candidate output is opened.

## Supply vs demand

The engine groups supply by:

- target gender;
- age band.

Demand is derived from each ready seeker's configured partner preferences:

- gender criterion;
- age criterion.

If a criterion is IGNORE or absent, it does not artificially narrow demand.

Current age bands:
- 18–23
- 24–28
- 29–35
- 36–45
- 46+

For every seeker-gender → target-gender → age-band segment the engine calculates:

- demand;
- supply;
- gap = max(0, demand - supply);
- coverage percent.

Rows are sorted by the largest deficit first.

## Acquisition insights

The report returns the largest current deficits as marketing insights so acquisition can answer:

“Кого сейчас не хватает в базе?”

The result is descriptive operational data, not a recommendation about which individual users should be matched.

## Attribution

Source breakdown separates:

- referral;
- UTM source;
- direct.

For every source it shows:

- registrations;
- completed active profiles;
- activation rate.

A referral takes precedence over UTM source for attribution reporting.

## Safety / data quality

Supply includes only users that are:

- ACTIVE;
- profile completed;
- questionnaire completed;
- partner preferences completed;
- photos completed;
- ACTIVE_FOR_MATCHING;
- ACTIVE_SEARCH or OPEN_TO_MATCH.

Paused, in-relationship, banned, incomplete and otherwise inactive profiles do not inflate launch supply.

## Admin console

The Phase 13 Audience balance section now uses this engine instead of only static counts.

No database migration is required for Phase 14.
