# Pi Engineering Universal System Graph MVP

## The product

Pi Engineering turns a system into a versioned evidence graph, then gives
people and agents the same deterministic way to inspect it. The first release
supports three high-value domains without separate products:

- software dependency and change-impact analysis;
- security entry-to-asset attack-path analysis;
- physical wiring-harness continuity, voltage, and current-capacity analysis.

The graph engine works offline. AI agents and MCP integrations can be added for
research and change proposals, while Pi keeps writes behind explicit review,
action hashes, and receipts.

## Five-minute investor walkthrough

```sh
pi-engineering system inspect examples/systems/software.json
pi-engineering system impact examples/systems/software.json api

pi-engineering system inspect examples/systems/security.json
pi-engineering system check examples/systems/security.json

pi-engineering system inspect examples/systems/wiring-harness.json
pi-engineering system check examples/systems/wiring-harness.json
pi-engineering system trace examples/systems/wiring-harness.json --from battery --to lamp-left
```

Use `--json` on any command to show that the same result is available to CI,
scripts, MCP wrappers, and other agents.

## Why it is different

Most engineering tools stop at one domain or produce opaque AI answers. Pi
separates deterministic system facts from model proposals. A dependency edge,
an attack route, and a physical wire use one graph contract, while each domain
adds its own checks. This makes cross-domain engineering possible without
giving an AI model direct authority over tools or files.

## MVP boundary

Included: versioned JSON graphs, strict validation, evidence hashes, topology
inspection, shortest-path tracing, bounded impact analysis, cycle and component
analysis, security attack paths, wiring route/current/voltage checks, rich CLI
views, JSON automation output, examples, persona profile, and review workflow.

Not yet included: CAD/EDA importers, live telemetry, schematic rendering,
collaborative cloud storage, organization accounts, and certified electrical or
safety compliance. Wiring results are engineering decision support and require
qualified review before physical deployment.
