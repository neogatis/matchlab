# Phase 15 — Pre-launch / waitlist

## Goal

Keep MatchLab useful before public matching is opened while preventing accidental candidate exposure.

## Central policy

PRE_LAUNCH_MODE defaults to true.

PRELAUNCH_MATCHING_ENABLED defaults to false.

When pre-launch is active and controlled matching is not enabled:

- registration remains available;
- questionnaire remains available;
- photo upload remains available;
- own compatibility profile remains available;
- waitlist remains available;
- candidate output is disabled;
- interest actions are disabled.

The candidate-output and interest-action rules use the same policy service, so direct service/API calls cannot bypass a UI-only flag.

When PRE_LAUNCH_MODE=false, candidate output is enabled regardless of the controlled-test flag.

## Waitlist status

A profile is WAITLIST-ready only when:

- account status is ACTIVE;
- profile is complete;
- questionnaire is complete;
- partner preferences are complete;
- photos are complete;
- eligibility is ACTIVE_FOR_MATCHING;
- relationship status is ACTIVE_SEARCH or OPEN_TO_MATCH.

The waitlist response is explicit about whether the profile is incomplete, waiting for launch, or actively matching. It does not claim that a candidate exists when candidate output is disabled.

## Own compatibility profile

The user can see a profile derived only from their own questionnaire answers.

The current v7-compatible summary contains:

- Ценности
- Ориентация на семью
- Потребность в близости
- Социальность
- Амбициозность

The formula preserves the existing v7 self-summary behavior for the 1–5 questionnaire scale.

The UI/API must label this as a description of answers, not a personality diagnosis or relationship-success prediction.

## Candidate protection

rank_candidates returns an empty set while pre-launch output is disabled.

The Phase 10 interest service uses the same centralized policy and fails closed by default.

No schema migration is required for Phase 15 because the settings table already exists.
