# MatchLab v7 — production baseline

This repository freezes the exact MatchLab v7.0 source currently deployed to Railway before the production architecture refactor.

## Baseline identity

- Version: `7.0`
- Source: `app/legacy/matchlab_v7.py`
- Exact production source size: `82720` bytes
- SHA-256: `c133d8944158e42dcff32feb9ea9fa43e77cacb6582fe61cd618c8bd2eb1544d`
- Runtime: Python 3.12
- Current mode: PRE-LAUNCH / WAITLIST
- Questionnaire: 64 unique questions
- Baseline CI: 10 automated tests

The legacy source is preserved exactly and materialized from the checked-in encoded baseline. GitHub Actions verifies the byte size, SHA-256, Python compilation and regression tests.

## Repository layout

- `app/legacy/matchlab_v7.py` — exact production v7 source.
- `app/legacy/encoded/` — reproducible encoded baseline parts.
- `scripts/reconstruct_baseline.py` — deterministic reconstruction.
- `scripts/verify_baseline.py` — exact source verification.
- `tests/` — baseline HTTP and matching regression tests.
- `docs/PRODUCT_SPEC.md` — product and engineering specification.
- `docs/ARCHITECTURE_AUDIT.md` — current architecture audit.
- `docs/TECH_DEBT.md` — prioritized debt register.
- `docs/ROADMAP.md` — phased production roadmap.

## Local run

```bash
python scripts/reconstruct_baseline.py
python scripts/verify_baseline.py
python -m unittest discover -s tests -v

mkdir -p data
MATCH_DATA_DIR="$PWD/data" PORT=8080 PRE_LAUNCH_MODE=true \
  ADMIN_IMPORT_KEY='local-dev-only' \
  python -u app/legacy/matchlab_v7.py
```

## Deployment status

The Git repository is ready and CI is green. The current public Railway service still runs the older image + environment-chunk bootstrap until the existing Railway service is connected to this repository. That cutover must be done without losing the current production URL or user data.

## Important

This baseline is a behavioral reference, not the final production architecture. PostgreSQL, migrations, object storage, hardened authentication/security and the versioned matching engine are subsequent phases.
