# Graph ship set manifest

Commit basis after freeze + production seals: see latest graph commits on `feat/platform-0.6-presets`.

## Runtime
- pi_workflow.py
- pi_engine.py (workflow binding + resource locks)
- pi_workspace.py (locks / ResourceBusy; shared)
- pi_app.py (workflow command)
- pi_live.py / pi_terminal.py (status rendering only)

## Packs
- workflows/*.json
- presets/*.json (default_workflow pointers)

## Tests
- tests/test_graph_scheduler.py
- tests/test_graph_production.py
- tests/benchmark_workflow.py (synthetic timing; not model IQ)
- tests/check_development_graph.py

## Docs
- GRAPH_UPGRADE.md
- GRAPH_VERIFICATION.md
- docs/GRAPH_ENGINEERING_SPEC.md
- docs/GRAPH_RELEASE_NOTES.md
- graph-development.json

## CI
- .github/workflows/pi-graph.yml
