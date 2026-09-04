# SPEC: Conflicts, Gifts and PAD Register (`conflicts-gifts-pad-register`)

Locked decisions, pinned stack, contracts. This document is the deepest authority on intent.

## Pinned stack
- Python `>=3.12`; ruff pinned exactly (`0.15.18`); mypy strict; deploy region `asia-southeast1`.
- Commons declared by tag in `pyproject.toml` (`pii-kit@v0.0.1`, `hex-service-kit@v0.0.1`, `agent-eval-kit@v0.0.1`, `review-kit@v0.0.1`) and pinned in the lockfiles to the 40-character COMMIT each tag resolved to. A tag can be moved; a commit cannot, so a lockfile that pinned the tag would let what installs change with no diff. `tests/unit/test_repo_artifacts.py` asserts the three-way agreement offline.
- The `hex-service-kit` pin is a security floor, not a preference: the kit checks the
  service-identity policy before the token, gates the zero-secret local opening on an exact
  profile match, and binds the loopback exposure guard over both HTTP and WebSocket scopes; it
  resolves every environment read in three states, so a variable set to empty fails closed
  instead of inheriting the unset default. Never move this pin backwards.
- Installs are LOCKED: `requirements-dev.lock` and `requirements-gcp.lock` are committed and are
  what `make install`, CI and the container image install. Nothing ships from an uncommitted
  resolve.

## What the service does

The register screens employee declarations (gifts and entertainment, outside business interests,
political donations) and personal-account-dealing trades against four deterministic detectors:
restricted-list matches, dealing-blackout breaches, MNPI-holding conflicts (all on exact
instrument identity, replayable from an `as_of` reference snapshot), and per-role, per-market
gift/entertainment thresholds from a fail-closed pack (`rulepacks/screening.yaml`, adopter-owned
policy). An unconfigured threshold is a gap that flags for review, never a pass. Each flagged
declaration becomes a `ConflictAssessment` (verdict, severity, fired rules, citations) that is
written to a tenant-scoped register, narrated by a grounded, schema-validated model that may only
restate engine findings, and routed to `human-review-console` for human sign-off. The restricted-list / blackout /
MNPI reference store is `conflicts-gifts-pad-register`-owned DATA (not code) and is served with an `as_of` over an
S2S-authenticated A2A feed (`GET /v1/reference/snapshot`) that `trade-comms-surveillance` consumes.

## Contracts
- **Identity**: a request's actor is a server-verified `Principal`; the client-supplied actor is
  discarded, and the tenant comes from the principal, never the request body. Local profile
  resolves a seeded dev persona from `X-Dev-Persona`.
- **Tenant isolation**: `GET /v1/register/{id}` serves a record only when the record's tenant tag
  and the verified principal's tenant are both present and EQUAL; anything else is 403 (never
  404). An UNTAGGED record is denied to everyone, and it cannot be written in the first place:
  every register store refuses a record with no tenant tag. Both rules live in `domain/tenancy.py`
  so every surface inherits them.
- **Redaction before audit**: the assessment service redacts PII (via `pii-kit`) before writing any
  audit record, and `AuditEvent` masks its own summary and every citation field at construction,
  so no surface can write a raw identifier to the WORM store by forgetting.
- **Determinism**: which screening rules fire, the CLEAR / FLAGGED outcome, the approve / escalate
  verdict and the severity are pure stdlib and replayable from an as-of reference snapshot; an LLM
  may narrate the fixed verdict and resolve a counterparty entity from free text, but never
  produces a number or a verdict.
- **Maker-checker (P-06) and routing (R8)**: a HIGH/CRITICAL result sets
  `requires_human_review=True` AND is routed through `ReviewRouterPort` to the `human-review-console` in the
  same request. The flag alone is not the escalation. The response carries `review_ref`, so a
  caller can tell a routed escalation from one that stopped here. The managed adapter refuses to
  run with no console configured rather than swallowing the escalation.
- **Profile**: resolved ONCE, at import, into a `ProfileChoice` and never a bare string. Three
  states of `CONFLICTSPAD_PROFILE`: UNSET is NO CHOICE (the SDK-free adapters
  still bind, but the seeded personas are refused, no service-to-service scheme is selected, every
  relaxation sees `unconfigured` and the exposure guard refuses every route to a non-loopback
  peer); SET AND EMPTY raises, so it can never inherit the unset behaviour; SET AND UNKNOWN,
  including a mis-capitalised value, raises. Only a deliberately named profile is honoured, and
  both raises happen before the process can serve anything.
- **Two derived postures, opposite directions**: `exposure_profile` drives every RELAXATION (CORS
  allowlist, the `X-Dev-Persona` allowed header, the HSTS baseline, the S2S scheme) and reads
  `unconfigured` when nobody chose; `bind_profile` drives the RESTRICTION (the loopback bound) and
  reads `local` when nobody chose. One string cannot do both without weakening one of them.
  Only `config.py` reads the variable.
- **End-user authentication is a property of the identity BINDING**, declared by the adapter
  (`VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`) and read by the loopback exposure guard. The
  service-to-service secret authenticates a calling SERVICE and no end user, so it takes no part
  in that decision: setting it closes the S2S routes and relaxes nothing.
- **Audit integrity**: the trail is hash-chained AND externally anchored. `audit_anchor_path`
  points at a file on a different volume that every append writes the chain head to; without it
  a truncated tail is undetectable, because the shorter chain still verifies. Once store and
  anchor disagree the service refuses to append rather than re-anchoring, so an ordinary write
  cannot launder a divergence. Re-anchoring is a deliberate operator action.
- **Agent surface**: optional but scaffolded. The A2A card at `/.well-known/agent-card.json` is
  built from the same tool table the runtime binds, so advertised skills and implemented tools
  are the same set. Tool results are masked for personal data before they return, because a tool
  result becomes model context (P-04); an API response to the caller who supplied the text is
  not. Nothing in `agent/` needs a runtime to import; `build_function_tools()` is the only seam.
- **Ports**: a port is registered in five places (`PORT_PROTOCOLS`, `DEFAULT_BINDINGS`, the
  `Container` accessor, `config/settings.yaml`, and the canonical-call table) and the contract
  suite asserts set equality across all five, in both directions.
- **Demo**: the demo is code and it is asserted. `scripts/walkthrough.py` narrates eight steps
  and, at each one, checks that the service actually reached the state the narration claimed;
  `--auto --headless` runs the same steps unattended in CI. A step exists in exactly two places
  (`demo.STEPS` and `walkthrough.CHECKS`) and the two are held equal, so a narrated claim nobody
  verifies cannot exist. The demo needs no browser engine, no network and no cloud.
- **UI identity**: the browser never asserts who it is. Every client-supplied actor, tenant,
  role, ACL and authorization header is discarded before a request is forwarded; identity is
  resolved server-side and the resolved headers are attached afterwards. The service credential
  is read from the server environment only. Framing and CORS are allowlists that refuse a
  wildcard however it is written, and an empty allowlist denies rather than opening up.
- **Eval**: `--mode smoke` is the offline pre-merge check; `--mode gate` is the `model-quality-gate` promotion
  authority. The gate fails closed.
- **Tests**: split into `unit`, `contract` and `integration`. The offline gate runs the first
  two; every integration module is marked, and that marking is itself enforced.

## Metrics and thresholds (smoke)
- `decision_accuracy >= 0.80`
- `pii_safety >= 0.99` (pack scan + pack-independent planted-literal check)
