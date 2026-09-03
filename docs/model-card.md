# Model card: Conflicts, Gifts and PAD Register (Rgc11)

This is a STARTER model card. It records the model boundary as built and the controls that must
be completed before a managed deployment. The deterministic screening engine is the system of
record; the model is a bounded, replaceable component with two narrow jobs.

## What the model does, and does not do

- **Does**, job one: resolve a counterparty entity from the free text of a declaration
  (`domain/ingestion_service.py`). It is asked for a JSON object matching
  `COUNTERPARTY_SCHEMA`, and the answer becomes an enrichment label only.
- **Does**, job two: draft the cited rationale for a verdict the engine has ALREADY fixed
  (`domain/assessment_service.py::_narrate`). It restates which rules fired and why.
- **Does NOT**: produce the amount, the effective date, the instrument identity, the reference
  snapshot, which rules fired, the CLEAR or FLAGGED outcome, the severity, the approve or
  escalate verdict, or the review requirement. Normalisation of every screening input is
  deterministic (`domain/ingestion_service.py`), and the decision is pure stdlib over that plus
  an `as_of` reference snapshot (`domain/screening_engine.py`). With the offline stub bound,
  every consequential field of an assessment is identical, so a model change cannot move a
  verdict.

## Boundary and validation

- The model is reachable through exactly one port, `ports/llm.py`, whose whole surface is
  `generate(prompt: str, *, schema: dict | None = None) -> str`. There is no second model seam.
- **The entity reply is discarded on any failure.** A reply that is not JSON, is not an object,
  or whose `counterparty` is not a non-empty string is dropped, and ingestion falls back to the
  declaration's structured `counterparty` field. A bad or adversarial reply changes an
  enrichment label and never a screening input.
- **The rationale is checked against the engine's own figures.**
  `domain/assessment_service.py::is_grounded` requires every number in the draft to appear in the
  engine's finding reasons or in the `as_of` date. A draft that carries a figure from neither is
  a fabrication and the draft is dropped, never repaired; `deterministic_summary` is used
  instead, which is grounded by construction because it is composed from the findings.
- Personal data is masked before the audit write, before a review payload leaves the process, and
  before a tool result can enter a model's context (`domain/pii.py`, `agent/tools.py`,
  `adapters/_review_payload.py`).
- Every flagged assessment sets `requires_human_review` and is routed to Hrz7 (rule R8) in the
  same call; nothing auto-executes, and nothing auto-approves.

## Adapters and profiles

| Profile | LLM adapter | Behaviour |
|---|---|---|
| `local` | `adapters/local/llm.py` | Deterministic and SDK-free. For an entity prompt it extracts the first `(FICTIONAL)`-marked entity from the text and returns empty when it finds none; for a rationale prompt it echoes the deterministic baseline the service already computed. It only ever restates what it was given, so it cannot produce a number the engine did not. |
| `gcp` | `adapters/gcp/llm.py` | Vertex AI via `vertexai.generative_models.GenerativeModel`, imported lazily inside the method. The model id is the literal `"gemini-3.5-flash"` in the adapter. |
| `onprem` | `adapters/onprem/llm.py` | Fail-fast placeholder: raises, naming the client-hosted model gateway to bind, and noting that screening does not depend on it. |

The offline stub deliberately does not invent prose beyond the facts. A stub that wrote freely
would be a second, kinder narrator that the managed path does not share, and the offline gate
would stop exercising the grounding check the managed path depends on.

## Remaining controls (TODO, repo owner)

- **Model id, version and region** (P-07): `"gemini-3.5-flash"` is a hard-coded literal in
  `adapters/gcp/llm.py`, not configuration and not a pinned version. Lift it into
  `config/settings.yaml` behind a `CONFLICTSPAD_`-prefixed variable, confirm the id is served in
  your deployment region, pin the exact model and version, and record it here. Gemini model ids
  are regional and an unavailable one fails at call time rather than at boot.
- **The adapter is untested against a live service.** `VertexLlmAdapter.generate` carries
  `# pragma: no cover - needs live GCP`, so the request shape, the schema handling (the `schema`
  argument is accepted and currently unused by this adapter) and the response mapping have never
  been exercised. Add an integration test under `tests/integration/` before relying on it.
- **Budget, rate limit and a kill switch** (P-10, P-11): there is no per-tenant token budget, no
  request rate limit, and no switch that forces deterministic-only operation. The fallback paths
  exist (a rejected entity reply already falls back to the structured field, a rejected rationale
  to the deterministic summary), but nothing yet lets an operator disable the model deliberately.
- **Evaluation of the live model**: the offline eval scores the deterministic pipeline with the
  stub bound against the golden cases, including `extraction_accuracy` for the entity resolution
  and `groundedness` for the rationale. Add a managed-profile run, registered with the Hrz4
  promotion gate (P-08, rule R5), that scores the same metrics with the real model bound.
- **Prompt-injection screening** (rule R1): the Hrz1 guardrail gateway is not bound. An employee
  writes the declaration narrative the entity prompt is built from, so that text is untrusted
  input by definition. Screen it before it reaches `IngestionService`, and fail closed to the
  structured field when the screen is unavailable.
- **Reasoning trace**: `COMPLIANCE.md` P-07 records that a model's reasoning trace should be
  audited alongside its output. Today the audit record carries the redacted summary and its
  citations, not the prompt and reply pair.

Until these are complete the system is safe to run offline (deterministic engine plus the stub)
and the managed model path is not production-cleared. Note separately that the managed profile as
a whole is gated by `managed_readiness.py`: the BigQuery feeds and the Firestore register store
are still construction-only, and both the API preflight and
`infra/terraform/managed_readiness.tf` refuse a managed serving path until they are not.
