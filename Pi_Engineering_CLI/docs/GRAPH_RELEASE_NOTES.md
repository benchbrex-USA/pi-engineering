# Graph release notes — production seal

**Date:** 2026-09-15  
**Branch:** feat/platform-0.6-presets  

## What changed
- Froze graph runtime/tests/docs into git (no longer untracked drift).
- Added `inspection_schema: 1` to offline workflow inspection JSON.
- Added `tests/test_graph_production.py`: side-effect proofs, resume matrix, pack/persona load, all-success join.
- Added CI workflow `.github/workflows/pi-graph.yml` (ubuntu/macOS × Python 3.11/3.12).

## What did not change
- Terminal UI/UX/design language
- Authority model (propose → approve → execute → verify)
- No distributed workers, any/quorum joins, or typed graph compiler
- Legacy/companion modules retained

## Verify
```bash
cd Pi_Engineering_CLI
.venv/bin/python -m unittest tests.test_graph_scheduler tests.test_graph_production -v
.venv/bin/pi-engineering workflow workflows/implement-review.json --validate --json
```
