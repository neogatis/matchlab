# Phase 7 — Matching engine v1

## Goal

Create one deterministic source of truth for mutual matching. AI does not decide who is eligible or who matches.

Algorithm version: `mutual-v1`.

## Pipeline

1. Eligibility
2. Mutual basic gender direction
3. Block check
4. User A HARD criteria against B
5. User B HARD criteria against A
6. Questionnaire compatibility by category
7. Mutual IMPORTANT/PREFERENCE score
8. Activity score
9. Readiness score
10. Final mutual-fit score and ranking

If a HARD criterion cannot be evaluated because required target data is missing, the pair does not pass that HARD criterion.

## Eligibility

Both profiles must be:
- 18+
- in a market with matching enabled
- ACTIVE_SEARCH or OPEN_TO_MATCH
- ACTIVE_FOR_MATCHING
- profile completed
- questionnaire completed
- partner preferences completed

PAUSED, IN_RELATIONSHIP and NOT_ACTIVE profiles are excluded before scoring.

## Compatibility categories

The 16 v7 questionnaire sections are mapped once into the 8 product categories:

- values_score: Ценности, Деньги
- relationship_score: Отношения, Эмоциональная близость
- family_score: Семья, Дети
- lifestyle_score: Образ жизни, Привычки
- communication_score: Конфликты, Социальность
- personality_score: Обо мне, Характер, Личное пространство
- future_score: Работа и амбиции, Жизненные планы
- interests_score: Интересы

For the current 1–5 scale, similarity is deterministic:
`100 - 25 * abs(answer_a - answer_b)`.

## Soft preference score

- IMPORTANT weight: 2
- PREFERENCE weight: 1
- HARD: used only as an eligibility gate
- IGNORE: omitted

Soft criteria with missing target data are excluded from the denominator rather than treated as a negative signal.

## Activity

Activity is derived from the newest of:
- session last_seen_at
- product event
- profile updated_at

The score decreases in explicit recency buckets and does not use opaque ML.

## Final score

`60% questionnaire compatibility + 25% mutual soft preferences + 10% activity + 5% readiness`.

This score is an internal ranking signal, not a scientific probability that a relationship will succeed.

## Distance

For v1, distance uses market/city centroid coordinates rather than precise user GPS coordinates. This supports city-level matching without collecting precise location. A HARD distance criterion fails if distance cannot be evaluated.

## Privacy

Raw answers and raw partner preferences are internal matching inputs and are not returned by candidate ranking.

Nationality is evaluated only when the user explicitly provided it; it must never be inferred from name, face, photo, language or other proxies.

## Ranking behavior

`rank_candidates` defaults to 5 results and refuses limits above 20, preserving the product principle of a small set of relevant candidates rather than an endless feed.

## Tests

Synthetic-user tests cover:
- mutual fit
- one-sided HARD conflict
- reverse HARD conflict
- paused profile
- in-relationship profile
- blocking
- age filtering
- distance filtering
- soft-preference scoring
- category compatibility
- activity
- ordered ranking
- large candidate pool with small output
