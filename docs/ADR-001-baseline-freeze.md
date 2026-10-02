# ADR-001 — Freeze the current v7 production baseline before refactoring

## Status
Accepted for Phase 1.

## Context
The currently deployed MatchLab v7 application is reconstructed from encoded Railway environment variables and executed from /tmp. This makes source history, review, automated testing and reliable rollback difficult.

## Decision
Preserve the exact production source and verified hash before architecture refactoring. Future work moves incrementally behind tests and migrations rather than rewriting the product in one change.

## Consequences
- Existing behavior remains auditable and reproducible.
- Later phases can compare new behavior with the frozen baseline.
- The legacy implementation remains explicitly marked as non-production architecture until replaced.
