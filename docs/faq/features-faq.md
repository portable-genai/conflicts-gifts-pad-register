# Features FAQ

For a product owner, a conduct-risk lead or a delivery manager deciding what this system does,
what it refuses to do, and where its responsibility ends.

### What does it actually do?

Given an employee declaration or a personal-account-dealing trade, it produces a cited conflict
assessment in four deterministic steps and one narrated one:

1. **Normalisation** (`domain/ingestion_service.py`): deterministic code fixes the amount, the
   effective date and the instrument identity, which are the only fields a screening decision
   consumes. The model resolves the counterparty entity from free text, under schema validation,
   with the structured field as the fallback.
2. **Reference snapshot** (`domain/reference_models.py` over `ReferenceStorePort`): the
   restricted symbols, dealing blackouts and MNPI holdings whose effective window covers the
   declaration's `as_of`. Replaying the same `as_of` reproduces the same snapshot byte for byte.
3. **Screening** (`domain/screening_engine.py`): four detectors, each a named rule with a stable
   id, recording exactly which fired and why. `restricted_list` and `blackout_window` match on
   the instrument identity rather than the free-text name, so an adversarial near-miss name
   cannot match; `mnpi_conflict` is the most severe, because dealing on inside information is
   market abuse; `gift_threshold` compares a gift or entertainment amount to the per-role,
   per-market limit in the pack.
4. **Verdict** (`domain/assessment_service.py`): FLAGGED becomes ESCALATE, CLEAR becomes APPROVE.
   The engine fixes it; nothing downstream can move it.
5. **Rationale**: prose that restates the findings above for a reviewer. It computes nothing.

### What is deterministic, and what does the model write?

Everything consequential is deterministic. Which rules fired, the CLEAR or FLAGGED outcome, the
severity and the escalation are pure stdlib over normalised facts plus the `as_of` snapshot, so
the same declaration and the same snapshot always produce the same assessment. The model does two
things only: it resolves a counterparty entity during ingestion (discarded on any schema failure,
falling back to the structured field), and it drafts the rationale for a verdict that is already
fixed. `is_grounded` rejects a rationale that cites a figure the engine did not produce, and the
deterministic summary is used instead. With the offline stub bound, every consequential field is
identical. See [`../model-card.md`](../model-card.md).

### What will it refuse to do?

- **It will not pass an unconfigured threshold.** A gift or entertainment combination the pack
  does not price is a GAP that flags for review, never a pass. Adding a market you have not
  priced cannot wave its gifts through.
- **It will not auto-approve a flag.** A FLAGGED assessment sets `requires_human_review` and is
  ROUTED to the Hrz7 console in the same call that produced it (rule R8), on every surface.
- **It will not start on a broken policy pack.** An unreadable pack, an unknown declaration kind,
  a limit citing an undefined citation id or a limit with no threshold raises `ScreeningPackError`
  at load. A screening gate on a silently empty rule set would wave everything through.
- **It will not let one tenant read another's register.** `get` is a raw fetch and the DOMAIN
  compares the record's tenant to the verified principal's, denying with 403 rather than 404, so
  the store cannot be probed with an id generator.
- **It will not answer without provenance.** Every assessment carries a `Citation`.

### Which surfaces expose it?

Five, and they behave the same because they share one domain service built through
`assembly.build_assessment_service` rather than reimplementing it: the FastAPI app
(`POST /v1/assess`, `GET /v1/register/{assessment_id}`), the argparse CLI
(`conflicts_gifts_pad_register screen --tenant demo-bank`), the agent tools
(`assess_declaration`, `verify_audit_trail`, advertised on the A2A card at
`/.well-known/agent-card.json`), the embeddable `ui/` micro-frontend, and the eval harness. Each
routes escalations in the same call, so rule R8 does not hold on four surfaces out of five.
There is a sixth, non-decisioning surface: `GET /v1/reference/snapshot`, the service-authenticated
A2A feed Cmp1 reads.

### What does this repo own, and what does it integrate?

| Concern | Owner | How this repo touches it |
|---|---|---|
| The restricted list, dealing blackouts and MNPI holdings | **Rgc11 (this repo)** | OWNED here, schema and all (`domain/reference_models.py`), and served with an `as_of` over `GET /v1/reference/snapshot`. |
| Trade and communications surveillance, market-abuse investigation | **Cmp1** trade and comms surveillance (`trade-comms-surveillance`) | it CONSUMES this repo's reference snapshot over A2A. This repo screens declarations; it does not watch order flow or chat. |
| Human review and maker-checker | **Hrz7** human review console | `ReviewRouterPort` over the shared `review-kit` (`HRZ_HUMAN_REVIEW_URL`). This repo produces escalations; it does not render a queue. |
| Model and agent promotion | **Hrz4** AI quality and model risk | `eval/run_eval.py --mode gate` asks Hrz4 (`CONFLICTSPAD_QUALITY_URL`); the offline smoke mode never promotes. |
| Traces and the immutable audit sink | **Hrz5** agent observability | `AuditSinkPort` and `ObservabilityTracerPort`; `OTEL_EXPORTER_OTLP_ENDPOINT` selects the Hrz5 collector. |
| Agent discovery and entitlements | **Hrz3** agent registry | this agent publishes a card; the registry owns discovery. |
| Prompt-injection defence and output filtering | **Hrz1** agent guardrail gateway | **not wired today.** It becomes mandatory the moment untrusted declaration narrative reaches the model (rule R1). |
| Grounded retrieval over an enterprise corpus | **Hrz2** enterprise knowledge base | not wired today; nothing here retrieves. |

### Can I demo it without a cloud project?

Yes, and the demo is code rather than a deck. `make demo` runs a presenter-paced walkthrough over
eight steps (opened, routine, escalation, redaction, review queue, audit, tamper, portability) on
its own loopback server; `make demo-selftest` runs the same arc headless and asserts every
narrated claim, so a claim that stops being true fails a build rather than a meeting;
`make demo-static` renders the same audit-first panels to static HTML for screenshots.

### What is not built yet?

The honest list is [`../practices-audit.md`](../practices-audit.md) and the `TODO (repo owner)`
rows in [`../../COMPLIANCE.md`](../../COMPLIANCE.md). The three that matter most for a production
decision: the managed store and feed adapters are still construction-only (they are listed in
`managed_readiness.py`, and the Terraform refuses to plan a serving edge while that list is
non-empty), the Hrz1 guardrail binding is unwired, and this repo's metric bundle is not yet
registered with Hrz4 so `--mode gate` has no authority to ask.
