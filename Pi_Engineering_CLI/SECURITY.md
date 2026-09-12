# Security and deployment boundary

Pi is a single-user local CLI, not a hosted tenant-isolation service. Project
configuration and registered executables are trusted operator inputs. Model
responses, documents and MCP observations are untrusted evidence.

## Controls

- Exact tool allowlists, argument validation, approval/config/schema hashes and
  one-hour approval expiry precede effectful dispatch.
- SQLite checkpoints are written before dispatch. Unknown external outcomes do
  not automatically retry. A remote success response is not business verification.
- Codex runs as a proposal adapter with native tools disabled. Event output is
  memory-bounded; subprocesses are terminated on cancellation/timeout. This is
  not a defense against a compromised local Codex executable.
- Workspace reads reject excluded paths and symlinks. State configuration, locks,
  SQLite databases and journal symlinks are rejected. Same-user adversarial races
  are outside this boundary; OS sandboxing is not implemented.
- HTTP MCP uses HTTPS except loopback, no redirects or inherited proxy settings,
  and credentials supplied through named environment variables. Stdio MCP servers
  and registered check commands run as the OS user; install only reviewed code.
- Backups use AES-256-GCM and scrypt. Active state is not application-encrypted.
  Use device encryption and OS permissions, and exclude state from version control.
- Customer qualification executes only operator-classified read tools, pins input
  schemas, validates response contracts, and stores hashes/status instead of raw
  arguments, observations or credential-bearing errors.

## Data handling

Selecting a hosted model transmits task input and allowed tool observations to
that provider. Grant workspace/knowledge/memory tools only when the data is
authorized for that destination. The current refusal to send private playbook
excerpts remains in effect; it was not bypassed by these qualification changes.
Deleting memory or sources removes them from active retrieval, not existing task
history, provider retention, or backups. Do not store credentials in prompts.

## Dependency maintenance

0.3.1 replaces cryptography 46.0.7 with 50.0.1 following advisory findings.
See the upstream [changelog](https://cryptography.io/en/latest/changelog/).
Pi uses AESGCM and scrypt, not the PKCS7 or X.509 verifier APIs mentioned in
several advisories; upgrading also updates the bundled OpenSSL dependency.

Reproduce automated checks:

```sh
python3 -m pip_audit . --progress-spinner off
python3 -m bandit pi_app.py pi_workspace.py pi_engine.py pi_tools.py pi_models.py pi_operations.py pi_knowledge.py pi_workflow.py pi_server.py pi_terminal.py pi_qualification.py
```

Scanner results are time-bound, heuristic evidence, not penetration testing or a
guarantee that no vulnerabilities exist. Audit the actual deployment environment
as well as newly resolved package metadata.

## Deployment acceptance

Before use with a customer account, independently classify permitted reads,
provision least-privilege credentials, pin its schemas, and run response contracts
that assert tenant identity and expected business fields. A negative-authorization
test should use explicitly provisioned test credentials, never production writes.
Rehearse encrypted recovery and protect the passphrase separately.

An independent assessor and representative users must own their own findings and
acceptance decisions. Automated checks performed by the implementation agent must
not be described as an independent assessment. No external reviewer has signed
off this release. No private customer account has been qualified.

For a suspected compromise: stop Pi and its configured local servers, revoke the
affected credentials at the provider, preserve the state directory for authorized
investigation, and restore only reviewed code/state. Do not replay unresolved
effects until their remote status has been independently checked.
