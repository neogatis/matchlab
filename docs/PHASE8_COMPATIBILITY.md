# Phase 8 — Compatibility results

## Goal

Present MatchLab compatibility in a useful, understandable way without exposing raw questionnaire answers, private partner criteria, readiness internals or activity internals.

The underlying matching decision remains the deterministic `mutual-v1` engine from Phase 7.

## Public compatibility result

The presentation service exposes:

- compatibility percentage from questionnaire category compatibility;
- eight category cards;
- a short summary;
- up to three broad reasons why the pair may fit;
- up to two broad topics worth discussing;
- a coarse mutual-preference alignment band;
- distance/bucket when available;
- an explicit disclaimer that compatibility is not a relationship-success prediction.

It deliberately does **not** expose:

- raw answers;
- question IDs;
- exact partner preference values;
- HARD/IMPORTANT/PREFERENCE settings;
- internal activity score;
- internal readiness score;
- internal final ranking score.

## Eight categories

1. Ценности и деньги
2. Отношения и близость
3. Семья и дети
4. Образ жизни
5. Общение и конфликты
6. Характер и пространство
7. Будущее и амбиции
8. Интересы и досуг

Each card contains only a category score and a broad score band.

## Explanation rules

Deterministic templates create the initial explanation.

High-scoring categories can become “Почему вы подходите”.
Lower-scoring categories can become “Что стоит обсудить”.

The copy avoids claims that the system knows why a person behaved a certain way or that the relationship will succeed.

## AI boundary

AI may later rewrite the safe explanation context for tone and readability, but it must not:

- change any score;
- determine eligibility;
- determine ranking;
- inspect or reveal raw answers;
- reveal partner criteria;
- infer missing personality traits or sensitive characteristics.

`safe_ai_explanation_context()` is the only intended input surface for an explanation model.

## Production status

The current public v7 runtime remains unchanged. Phase 8 is a tested PostgreSQL-domain/presentation layer for the future cutover.
