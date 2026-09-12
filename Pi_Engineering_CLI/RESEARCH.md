# Research and product correction

Reviewed 2026-09-12. Source documents are evidence, not runtime instructions.

## Commissioning evidence

The supplied Pi Engineering Playbook and Course describes an integrated system
of experience, graphs, bounded loops, context, memory, retrieval, tools, models
and assurance. Pages 7-8 explicitly identify ServiceDesk Pi as a fictional,
offline teaching case. Pages 11-16 require distinct proposed/executing/verified
states, meaningful consent, observable outcomes and durable graph boundaries.
Implementing only the ticket example was the wrong interpretation of the product.

## Design reference

[Yann-Edern Gillet: Designing for the Command Line Interface](https://yannglt.com/writing/designing-for-command-line-interface)
describes Specify's CLI components and its use of Ink and Chalk. Relevant design
decisions are ANSI foreground/background contrast, character-based spacing,
aligned context fields, nested task feedback, and real operation status. The new
renderer applies those design decisions with Rich in the existing Python stack.
The reference is not a specification for a dashboard or a gallery as the primary
experience. Exact pixels depend on the operator's terminal font and color theme.

## Graph engineering

[Google ADK workflow agents](https://adk.dev/agents/workflow-agents/) documents
control of subagent execution and links the current graph-based workflow model.
Its sequential, loop and parallel patterns are architectural alternatives, not
evidence that multi-agent work automatically improves outcomes.

Pi now exposes explicit legal node transitions and recorded checkpoints, and
validates dependency DAGs with Python's graphlib.TopologicalSorter. Recovery,
approval and unresolved dispatch are actual states. Independent DAG nodes are
concurrent with bounded parallelism and durable joins. No speed/intelligence
multiplier versus ADK was measured.

## Protocol and model integration

[Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
now documents v2 as the stable main line and v1 as a maintained branch. The
installed and tested SDK here is 1.29.1, pinned explicitly instead of mixing API
generations. Pi uses its stdio, Streamable HTTP, schema and server lifecycle
implementations. Both transports were exercised against real SDK server processes.

[Ollama chat API](https://docs.ollama.com/api/chat) and
[tool calling](https://docs.ollama.com/capabilities/tool-calling) define the model
adapter's actual request/response format. Model API transport was verified against
a local contract fixture; that is not a live model-quality evaluation.

[Claude CLI reference](https://code.claude.com/docs/en/cli-reference) was checked
when assessing available model access on this Mac. The installed Claude CLI
reports loggedIn=false. It is not used as a hidden provider or as a substitute for
Pi's configured Ollama endpoint.

## Useful prior work retained

Approval hashes, checkpoint/receipt separation, transaction-oriented storage,
tenant-isolation tests for the historical ticket system, and explicit untrusted
evidence boundaries informed this correction. The old teaching implementation and
its data remain inspectable locally. They are excluded from the product wheel.
The new runtime does not claim the old tenant model. It implements its own
workspace-scoped FTS5 BM25 retrieval with provenance and source validation.

## Release 0.3 integration research

[Codex non-interactive operation](https://learn.chatgpt.com/docs/non-interactive-mode)
documents structured output and reuse of authenticated CLI access. Pi uses an
ephemeral read-only invocation and an output schema to return model proposals
to its own governed dispatcher. Native tool events are rejected. Existing login
was exercised with public synthetic retrieval, memory and approved-write cases.

[DeepWiki MCP](https://docs.devin.ai/work-with-devin/deepwiki-mcp) documents a
public Streamable HTTP service. Pi discovered it and called read_wiki_structure
for modelcontextprotocol/python-sdk. This proves one external read integration,
not private customer-account authorization or business write semantics.

## Evidence limits

Local transport, graph and approval checks establish specific behaviors, not a
production certification. The final release report lists live-model, external
integration, usability and deployment qualification still required. The wider
playbook's model training, infrastructure scaling and research curriculum are not
implemented merely by naming CLI agents after them.
