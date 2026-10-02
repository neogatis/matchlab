# MatchLab v7 — production baseline

This repository freezes the exact MatchLab v7.0 source currently deployed to Railway before the production architecture refactor.

## Baseline identity
- Version: 7.0
- Source: app/legacy/matchlab_v7.py
- Exact production source size: 82720 bytes
- SHA-256: c133d8944158e42dcff32feb9ea9fa43e77cacb6582fe61cd618c8bd2eb1544d
- Runtime: Python 3.12
- Current mode: PRE-LAUNCH / WAITLIST
- Questionnaire: 64 unique questions

The baseline file is intentionally not refactored. It exists as the reproducible reference while infrastructure is replaced incrementally.

See docs/ for the architecture audit, tech debt, product specification, and migration roadmap.
