# Adopting this repo as your base

This repository (`conflicts-gifts-pad-register`, the Conflicts, Gifts and PAD Register) is a **common base** that a bank
or other regulated institution forks to build its own **employee-conduct screening register**: a
service that ingests gift, entertainment, outside-interest, political-donation and
personal-account-dealing declarations, normalises them deterministically, screens each one
against an `as_of` snapshot of the restricted list, the dealing blackouts and the MNPI holdings,
and records a cited, escalatable assessment a second line can replay. It ships a reusable
hexagonal core (a pure-stdlib domain, typed ports, three swappable adapter profiles, a green
offline gate) plus a fully worked conflicts / PAD vertical you can keep, retune, or replace with
your own conduct policy.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and topology),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding an adapter, adding a port), the
> [`faq/`](faq/) directory, [`model-card.md`](model-card.md) (the model boundary),
> [`practices-audit.md`](practices-audit.md) (the per-check verdict).

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and the conflicts vertical is
a physical module split with an enforced dependency direction (practices-audit check A7).
`domain/kernel.py` owns the vertical-neutral contracts and imports no vertical ARTIFACT, so you
can import it without loading a line of conduct logic; `domain/models.py` holds only the `conflicts-gifts-pad-register`
artifacts and re-exports every kernel name. The one thing the kernel does reach for is
`domain/pii.py`, the jurisdiction list, because `AuditEvent` masks its own content at
construction and a boundary that cannot name the rows it masks with is not a boundary.

| Layer | Where | For a different conduct regime |
|---|---|---|
| **Vertical-neutral machinery** | `domain/kernel.py` (`Citation`, `AuditEvent`, `Severity`, `Decision`, `utcnow`), `domain/errors.py`, `domain/tenancy.py` (the tenant read and write rules), every Protocol in `ports/`, the container wiring in `config.py`, the assembly helpers in `assembly.py` | keep untouched |
| **Policy (your numbers and sets)** | the reference threshold pack `src/conflicts_gifts_pad_register/rulepacks/screening.yaml` (per-role, per-market gift and entertainment limits, loaded by `screening_pack.py`), the jurisdiction list in `domain/pii.py`, the metric thresholds in `eval/run_eval.py` | change deliberately (see section 4) |
| **Vertical (the artifacts themselves)** | the `conflicts-gifts-pad-register` models in `domain/models.py` (`Declaration`, `DeclarationKind`, `Instrument`, `NormalizedDeclaration`, `ConflictAssessment`), the reference schema in `domain/reference_models.py` (`RestrictedSymbol`, `BlackoutWindow`, `MnpiHolding`, `ReferenceSnapshot`), the four detectors in `domain/screening_engine.py`, the entity resolution in `domain/ingestion_service.py`, the orchestration in `domain/assessment_service.py`, the local fixtures and the eval golden set | rewrite for your regime |

If your product is another *normalise then screen against reference data* gate, most of the
hexagon, the three profiles, the deterministic-verdict pattern, the eval gate and the `human-review-console` review
routing transfer directly; you replace the detectors and the reference schema, and retune the
threshold pack and the taxonomy.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): the vertical-neutral machinery listed above, `ports/`,
  `tests/contract/`, the eval harness mechanics (`eval/run_eval.py`), the CI workflows, the
  hexagon wiring (`config.py` `Container`) and the deploy stack in `infra/terraform/`.
- **Adopter-owned** (yours; expect to edit): `config/settings.yaml` *values*, the threshold pack
  `rulepacks/screening.yaml`, the local fixtures and the golden eval dataset,
  `adapters/onprem/*`, UI theming and branding, `infra/terraform/terraform.tfvars`, and the
  regulator crosswalk section of `COMPLIANCE.md`.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name (`conflicts_gifts_pad_register`, which is
also the console script, so `conflicts_gifts_pad_register screen` becomes your command), the
`CONFLICTSPAD_` env prefix (including the bare `CONFLICTSPAD` that
`infra/terraform/render.tf.json` carries so Terraform sets the same variable names on the
service), the cloud resource stem (`rgc11-svc`, the Terraform `name_prefix`) and the
distribution / git id in one pass. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_conflicts_register --env-prefix ACME \
    --resource acme-conflicts --dry-run

# Apply:
python scripts/rename_fork.py --package acme_conflicts_register --env-prefix ACME \
    --resource acme-conflicts --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

`--dist` defaults to the `--resource` value; pass it explicitly when your git id differs from
your resource stem. `--resource` is validated against the same regex the Terraform `name_prefix`
variable enforces, so a stem the stack would refuse fails here instead of at plan time. Add
`--include-docs` to sweep Markdown prose too. The catalog id `conflicts-gifts-pad-register` is left alone unless you
pass `--catalog-id`, so a fork stays traceable to the entry it descends from and to the
reference feed `trade-comms-surveillance` knows it by. The script deliberately does NOT touch the human decisions
below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** The build defaults to `asia-southeast1` (MAS / Singapore), chosen once
   and shared: `config/settings.yaml:region`, `infra/terraform/render.tf.json:render_region` and
   the Terraform `region` / `allowed_regions` pair. Set all of them to your in-country region,
   and re-run the residency tests in `infra/terraform/production_edge.tftest.hcl`, which refuse a
   region outside the allowlist at plan time. See [`runbook.md`](runbook.md).
2. **Identity / IdP.** This repo owns no login flow: the `gcp` profile verifies the IAP-injected
   assertion at the edge, `local` uses seeded dev personas, and `onprem` is a client IdP
   placeholder. Wire your issuer on the deployed service (auth is configured ON the service, not
   in this code) and set `CONFLICTSPAD_IAP_AUDIENCE`. An unset or emptied audience refuses every
   caller rather than verifying without one.
3. **The threshold pack (your gift and entertainment policy).**
   `src/conflicts_gifts_pad_register/rulepacks/screening.yaml` holds the limits as DATA: a
   threshold per declaration kind, per role and per market, each citing the policy instrument it
   comes from. Point `CONFLICTSPAD_SCREENING_PACK` at your own file rather than editing the
   reference pack, and keep the invariant the engine encodes: an UNCONFIGURED threshold is a gap
   that FLAGS for review, never a pass, so adding a market you have not priced cannot wave its
   gifts through. The loader is fail-closed, so a named-but-missing pack refuses to boot.
4. **The reference data (restricted list, blackouts, MNPI).** This is the one dataset `conflicts-gifts-pad-register`
   OWNS rather than reads, and its schema is therefore authoritative here
   (`domain/reference_models.py`). Load your real restricted symbols, dealing blackouts and MNPI
   holdings through `ReferenceStorePort` (BigQuery under `gcp`), each with an effective window,
   because `snapshot(as_of)` is what makes a screening decision replayable years later. `trade-comms-surveillance` consumes an `as_of` snapshot of exactly this shape over the
   A2A feed, so a schema change here is a contract change for it.
5. **Policy numbers your compliance function owns.** The jurisdiction list in `domain/pii.py`
   (which national PII rows are scanned, and in what order), the severity ladder
   `_SEVERITY_ORDER` in `domain/screening_engine.py`, and the eval thresholds in
   `eval/run_eval.py` (`decision_accuracy`, `extraction_accuracy`, `groundedness`,
   `pii_safety`). Those three are module-level today rather than a `policy:` settings section
   (practices-audit check B4); change them deliberately and add a test that pins your values.
6. **Reference data is fictional.** Every fixture (`tests/fixtures/sample_cases.py`,
   `adapters/local/_seed.py`, `eval/datasets/golden_cases.jsonl`) uses obviously fake employees,
   counterparties and `.example` domains, and the one national id exists solely so the redaction
   check has an independent literal to look for. Replace them with your own synthetic data. **Do
   not run against a real employee declaration feed or a real broker feed without your own
   security, privacy and employment-law sign-off**: a conflicts register holds staff personal
   data and trading positions, which is a stricter class than most GRC inputs.
7. **Eval golden set.** Rebuild `eval/datasets/golden_cases.jsonl` for your policy: a fork
   inherits a green gate that measures the WRONG thresholds until you do. The gate structure and
   the strict `pii_safety >= 0.99` metric are generic; the golden cases are yours.
8. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001),
   `infra/terraform/` (Org Policy, CMEK, a dry-run-first VPC-SC perimeter, the locked WORM log
   bucket) and the loopback-by-default binding before you expose anything. The WORM lock is
   irreversible: confirm `retention_days` before the first apply. Note that
   `infra/terraform/managed_readiness.tf` refuses to plan the serving edge while
   `managed_readiness.py` still lists construction-only managed operations, so implementing the
   BigQuery and Firestore adapters is a prerequisite for a managed deployment, not an optional
   extra.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches* are
owned by sibling platform services, and you should integrate rather than rebuild them (see
[`faq/features-faq.md`](faq/features-faq.md) for the full map). The `gcp` profile's adapters are
already thin clients to them:

- `human-review-console` human-review / maker-checker console: every `requires_human_review` escalation is
  routed to it over the shared `review-kit` (rule R8); you wire your endpoint
  (`HUMAN_REVIEW_URL`), you do not re-implement the console.
- `model-quality-gate` AI-quality / model-risk gate: owns promotion. `eval/run_eval.py --mode gate` is the
  client half (`CONFLICTSPAD_QUALITY_URL`) and refuses to run off the managed profile; the
  offline smoke mode mirrors the thresholds.
- `agent-observability` plus immutable WORM audit: audit events and trace spans go to it via
  `AuditSinkPort` and `ObservabilityTracerPort` (`OTEL_EXPORTER_OTLP_ENDPOINT` selects the `agent-observability`
  collector over direct Cloud Trace).
- `agent-registry`: this agent publishes its A2A card at
  `/.well-known/agent-card.json`; register it rather than inventing a discovery mechanism.
- `trade-comms-surveillance` trade and communications surveillance: the CONSUMER of this repo's reference snapshot,
  not a dependency of it. It reads `GET /v1/reference/snapshot` with an `as_of` over S2S. Keep
  that feed stable, and do not build a second restricted-list store on the surveillance side.

The guardrail gateway (`agent-guardrail-gateway`) is **not** integrated today. It becomes mandatory the moment
untrusted free text (an employee-written declaration narrative, say) reaches the model: see rule
R1 in [`../COMPLIANCE.md`](../COMPLIANCE.md). The enterprise knowledge base (`enterprise-knowledge-base`) is likewise
unwired, because nothing here retrieves.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set the region in all three places (settings, `render.tf.json`, tfvars) and re-ran the
      Terraform residency tests.
- [ ] Wired your IdP audience on the deployed service (this repo owns no login flow).
- [ ] Replaced the threshold pack with your own file behind `CONFLICTSPAD_SCREENING_PACK`,
      keeping the unconfigured-threshold-flags invariant.
- [ ] Loaded your restricted list, blackout windows and MNPI holdings through
      `ReferenceStorePort`, each with an effective window, and told `trade-comms-surveillance` the feed is live.
- [ ] Owned the policy numbers (PII jurisdictions, the severity ladder, eval thresholds) with
      your compliance function.
- [ ] Replaced every synthetic fixture and the seeded declaration and brokerage feeds.
- [ ] Rebuilt the eval golden set for your policy.
- [ ] Implemented the managed store and feed adapters, emptied
      `INCOMPLETE_MANAGED_OPERATIONS`, and flipped `managed_profile_implemented` in the same
      reviewed commit.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, `retention_days`, bind address).
- [ ] Wired your `human-review-console` review endpoint and decided which sibling services you integrate vs stub.
- [ ] Read [`model-card.md`](model-card.md) and closed its remaining controls before enabling the
      managed model.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
