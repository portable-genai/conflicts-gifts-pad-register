# Adoption FAQ

For an engineering lead forking this repo as their institution's conflicts and PAD base. The
step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?"
questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the package name (`conflicts_gifts_pad_register`, which is also
the console script, so the `screen` command is renamed with it), the `CONFLICTSPAD_` env prefix
(including the bare token that `infra/terraform/render.tf.json` carries, so Terraform sets the
same variable names on the service), the Terraform `name_prefix` resource stem (`rgc11-svc`) and
the distribution / git id in one pass. Preview with `--dry-run`, apply with `--yes`, then
recreate the venv, `make install`, and run `make gate`. The catalog id `conflicts-gifts-pad-register` is left alone
unless you pass `--catalog-id`, so a fork stays traceable to the entry it descends from and to
the reference feed `trade-comms-surveillance` knows it by. The script does the mechanical rename; the human decisions
(the threshold pack, the reference data, region, IdP, eval golden set) are the checklist in
`ADOPTING.md`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via **git tags**. The repo declares a core-vs-adopter-owned boundary
(`ADOPTING.md` section 2): upstream owns `domain/kernel.py`, `ports/`, `tests/contract/`, the
eval harness mechanics, CI and the Terraform stack; you own `config/settings.yaml` values, the
threshold pack in `rulepacks/screening.yaml`, the fixtures and golden set, `adapters/onprem/*`,
UI theming and `terraform.tfvars`. Rebase your adopter-owned changes onto each release rather
than merging `main` continuously, so conflicts stay in files you were told to expect.

### What do we have to supply that is not in this repo?

Four things, and none of them is code here:

1. **The threshold pack.** `rulepacks/screening.yaml` ships a reference set of per-role,
   per-market gift and entertainment limits in minor units. The instrument names it cites are
   real published sources; the numbers are illustrative, and your conduct function owns the real
   ones. Point `CONFLICTSPAD_SCREENING_PACK` at your own file rather than editing the reference.
2. **The reference data.** Your restricted symbols, dealing blackouts and MNPI holdings, loaded
   through `ReferenceStorePort` with an effective window on every entry. Offline it serves
   fictional entries; nothing screens meaningfully until this is real.
3. **The inbound feeds.** `DeclarationFeedPort` (employee declarations, free text plus structured
   fields) and `BrokerageFeedPort` (personal-account trades and holdings, already structured).
   These are deliberately separate ports because they come from different systems of record.
4. **The review console.** An `human-review-console` deployment reachable at `HUMAN_REVIEW_URL`. The managed
   router REFUSES to swallow an escalation when this is empty, so a fork cannot ship rule R8
   unwired and green.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and a contract test that enforces it. A port must be registered in
FIVE places or it runs with no enforcement at all: `ports/__init__.py` (`PORT_PROTOCOLS`),
`config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`, and a `PortCase` in
`tests/contract/canonical.py`. Then bind it in all three families.
`tests/contract/test_port_parity.py` asserts set equality across the five. See
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

### Can I retune the screening policy without touching engine code?

For the gift and entertainment limits, yes, and that is deliberate: they are pack DATA loaded by
`screening_pack.py` from a YAML file a compliance officer can read and diff, selected by
`screening_pack_path` in `config/settings.yaml`. The engine holds no monetary constant and never
learns a role's name or a currency. What is NOT yet configuration is the rest: the severity
ladder `_SEVERITY_ORDER` in `domain/screening_engine.py`, the PII jurisdiction list in
`domain/pii.py` and the eval thresholds in `eval/run_eval.py` are module constants, and there is
no `policy:` block in `config/settings.yaml` that carries them. That is the open B4 item in
[`../practices-audit.md`](../practices-audit.md). If your compliance function must own those as
configuration too, plan that small addition as part of adoption.

### What stops a managed deployment going live half-built?

`managed_readiness.py` lists the managed operations that are still construction-only (the
BigQuery declaration, brokerage and reference adapters, and the Firestore register store), and
the API preflight refuses to start a `gcp` process whose active bindings include one of them.
`infra/terraform/managed_readiness.tf` mirrors the same fact and refuses to plan the serving edge
while `managed_profile_implemented` is false. Emptying the tuple and flipping the Terraform local
belong in the same reviewed commit as the integration evidence, never earlier.

### Does the gate run for my fork out of the box?

Yes. `make gate` is offline, credential-free and network-free (ruff, ruff format, mypy strict,
the whole suite except integration, and the eval), and the CI workflow references no `secrets.`,
so a fork's build is green immediately. You add secrets only when you wire the `gcp` profile.
Note the eval measures the REFERENCE threshold pack and golden cases until you rebuild them for
your own policy; that is an explicit adoption step, not a silent pass.

### Will the demo rot after I diverge?

It is guarded, and the guard is inside the gate. A demo step lives in `demo.STEPS` and in
`walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two equal, so a claim the
demo makes but nobody verifies cannot exist. `make demo-selftest` runs the whole arc headless
over the real loopback server and exits non-zero when a claim stops being true; the hosted
check runs it and `make portability` on every pull request and every push to main. If
you diverge, keep the step keys and the `facts` dict the checks read.

### The eval reports 1.000. Should we believe it?

Only because each metric is proved able to report something else.
`tests/unit/test_not_falsely_green.py` hands the safety metric a planted mutant and fails the
build if it still passes, and `pii_safety` is scored twice, once through the shared pack scan and
once through an independent planted-literal oracle. A metric that cannot go red is not a metric.
The scores are also measured against the REFERENCE golden set, which is synthetic: rebuilding it
for your policy is an adoption step.

### What is still open?

[`../practices-audit.md`](../practices-audit.md) carries the per-check verdict and the work list.
The three that matter most before production: implementing the managed store and feed adapters
(nothing deploys until `managed_readiness.py` is empty), binding the `agent-guardrail-gateway`
(needed before untrusted declaration narrative reaches the model), and registering this repo's
metric bundle with `model-quality-gate` so `eval/run_eval.py --mode gate` has an authority to ask. The Terraform
stack is written, validated and tested against a mocked provider; it has never been applied.
