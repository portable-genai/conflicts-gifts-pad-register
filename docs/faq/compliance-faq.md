# Compliance FAQ

For compliance, conduct risk, model risk and the second line. The mapping table with a file
reference on every row is [`../../COMPLIANCE.md`](../../COMPLIANCE.md); this page answers the
questions that come back after reading it.

### Is a screening decision defensible in front of a regulator?

That is the reason it is pure code. Which rules fired, the CLEAR or FLAGGED outcome and the
severity come from `domain/screening_engine.py`, a stdlib module with no clock, no randomness and
no network, run against the reference snapshot effective on the declaration's own `as_of`. The
same declaration and the same `as_of` reproduce the same assessment years later, and the fired
rules are recorded by stable id with a `Citation` each. No model participates in the decision.
Three invariants matter for a review:

- **An unconfigured threshold flags.** A gift or entertainment combination the pack does not
  price is a GAP for a human, never a pass.
- **Identity matching is exact.** The restricted-list and blackout detectors match the instrument
  identity, not the free-text name, so a near-miss name cannot be used to slip past them.
- **MNPI outranks everything.** Dealing on inside information is market abuse, and the detector
  is graded accordingly.

The thresholds shipped here are a REFERENCE, not a legal position: the numbers are illustrative
and your conduct function owns the real ones.

### Who signs off a flagged declaration?

A human, always. `requires_human_review` and the call to `ReviewRouterPort.route` are one act,
not a flag plus an intention: `api/app.py`, `cli/main.py` and `agent/tools.py` all route in the
same call that produced the result, and `tests/unit/test_review_routing.py` asserts the routing
rather than the flag. A CRITICAL band demands two approvals
(`adapters/_review_payload.py`). Under the managed profile the router REFUSES when no console is
configured, so a deployment cannot swallow an escalation silently.

### Where does the data live, and is residency enforced or just documented?

Enforced at deploy time. The region is chosen once (`asia-southeast1`) and shared by the runtime
and Terraform: `infra/terraform/variables.tf` validates the region against the residency
allowlist at plan, `org_policy.tf` pins `gcp.resourceLocations` to that region's location group,
and every regional resource (the CMEK key ring, the WORM log bucket, the Cloud Run service) is
created in it. `infra/terraform/production_edge.tftest.hcl` is the standing proof: its
`reject_region_outside_the_residency_allowlist` and `residency_defaults_are_in_country` runs fail
if the allowlist stops refusing or a resource drifts off region, and they run against a mocked
provider so they need no project and no credentials.

### What about key management and least privilege?

One REGIONAL CMEK key with a 90-day rotation, and an explicit key binding for EACH service agent
that encrypts under it (Logging, Cloud Run, Vertex AI, Storage), because CMEK does not cascade
(`infra/terraform/kms.tf`). One serving identity holding four roles, each traceable to a bound
adapter, with `logging.logWriter` write only so the process cannot read back the WORM trail it
writes (`iam.tf`). Exportable service-account keys are forbidden by org policy rather than merely
avoided, and a key creation raises an alert if one happens anyway (`org_policy.tf`,
`monitoring.tf`).

### How long is the audit trail kept, and can it be edited?

180 days by default, and the variable refuses anything below 180. The Cloud Logging bucket is
LOCKED by default, which is irreversible: once applied, retention cannot be reduced and the
bucket cannot be deleted for the full window, not even with project-owner rights. Confirm
`retention_days` before the first apply, and confirm it against your employment-law retention
position as well as your regulatory one, because a conflicts register holds staff personal data.
DATA_READ audit logging is enabled too, so a read of the register is itself recorded: a trail
that records who was screened but not who read the result is half a trail.

Offline the same guarantee is earned differently: the log is hash-chained AND externally
anchored, because a truncated tail leaves a shorter chain that verifies perfectly. The retention
schedule and the legal basis for the trail are adopter-owned.

### What personal data does this system process?

More than most catalog systems, and it should be scoped accordingly: employee identities and
roles, gift and entertainment counterparties, and personal-account trading positions. That is
staff personal data plus market-sensitive position data. Whatever appears is masked before every
boundary (the audit write, the outbound review payload, and any tool result that could enter a
model's context), with the jurisdiction rows and their ORDER chosen in `domain/pii.py`. The
`pii_safety` metric holds this at `>= 0.99` and is proved able to go red. The MNPI holdings in
the reference store are deliberately NOT redacted, because they are the screening input rather
than an incidental identifier, which is why the A2A feed that serves them is
service-authenticated.

### What model-risk evidence exists?

[`../model-card.md`](../model-card.md) records the model boundary as built: the model resolves a
counterparty entity under schema validation and drafts a rationale for an already-fixed verdict,
both discarded on failure, and with the offline stub bound every consequential field is
identical. The offline eval (`eval/run_eval.py --mode smoke`) scores `decision_accuracy`,
`extraction_accuracy`, `groundedness` and `pii_safety` on every change, against the dataset's own
labelled oracle rather than the pipeline's verdict. What is NOT yet in place: the managed adapter
names `gemini-3.5-flash` as a literal rather than a confirmed and configurable pin, there is no
token budget, rate limit or kill switch, no live-model eval run has been registered with the `model-quality-gate`
promotion gate, and prompt-injection screening through `agent-guardrail-gateway` is not bound. Until those close, the
managed model path is not production-cleared and the deterministic path is what should be relied
on.

### Which regulations does this claim to satisfy?

None, on your behalf. The mapping in `COMPLIANCE.md` is to the CATALOG's own principles (P-01 to
P-13) and platform rules (R1 to R8). The instrument names in `rulepacks/screening.yaml` are real
published sources cited so a reviewer can trace a flag to its basis; they are short paraphrases,
not verbatim quotations, and none of them is legal advice. The crosswalk from a catalog row to
MAS TRM, CPS 234, CPS 230, HKMA or PDPA control ids, and the judgement that a control is
SUFFICIENT for a regulation, is explicitly adopter-owned: it depends on your risk appetite, your
regulator and your existing control library. No row in that document should be quoted as
regulatory assurance, and the second-line review of the deterministic policy in `domain/` is
bank-owned logic rather than a vendor default to inherit unexamined.

### What is still open at go-live?

The `Partial` and `TODO (repo owner)` rows in `COMPLIANCE.md`, each of which names exactly what
is missing. The ones that need a risk acceptance if you go live without them: the
construction-only managed adapters listed in `managed_readiness.py` (which the Terraform edge
gate refuses to serve past), rule R1 (the `agent-guardrail-gateway` binding), rule R5 and P-08 (the `model-quality-gate`
metric bundle), P-10 (timeouts, circuit breaker and a documented kill switch), and P-01's
private-egress rule, which depends on your own network rather than on this repo.
