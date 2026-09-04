# Security FAQ

For AppSec and security architecture. Every answer names the file that is the evidence, so the
review can read the control rather than the claim.

### Who is the actor on a screening decision, and can a caller assert it?

A server-verified `Principal`, always. `AssessRequest` (`api/schemas.py`) has no `actor` field
and no `tenant` field: the audit actor and the review maker both come from the identity adapter,
and every client-supplied actor, tenant, role, ACL and authorization header is discarded at the
browser boundary (`ui/lib/embed-policy.mjs`). Under the `gcp` profile the adapter verifies the
IAP-injected assertion against the configured audience, against IAP's own key set and against
the issuer (`adapters/gcp/identity.py`); an unset or emptied `CONFLICTSPAD_IAP_AUDIENCE` REFUSES
every caller, because `audience=None` means google-auth does not verify the audience at all and
would accept any Google-signed token from any project.

### What happens if the profile variable goes missing in production?

The process still binds the SDK-free adapters (the alternative is importing cloud SDKs that are
not installed), but nobody chose them, so every relaxation is withdrawn: the seeded dev personas
refuse to construct, no service-to-service scheme is selected, the dev CORS allowlist and the
`X-Dev-Persona` header are gone, the interactive docs are not registered, and the loopback
exposure guard refuses every route to any non-loopback peer. An emptied or mis-capitalised value
raises AT IMPORT, so the process fails to boot rather than serving on a posture nobody chose
(`config.py`, `tests/unit/test_profile_single_source.py`).

### Does setting the service-to-service token open anything?

No, and this is enforced rather than intended. The exposure guard's posture is derived from the
identity BINDING (the adapter declares `VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`), never
from a credential. `CONFLICTSPAD_S2S_TOKEN` authenticates a calling SERVICE and no end user.
`tests/unit/test_end_user_auth_posture.py` walks the guard's argument through the constants it
names and fails the build if a credential reappears at any depth, because it did once: setting
the token switched the guard off for the end-user routes it was protecting.

### Who can read the reference feed `trade-comms-surveillance` consumes?

`GET /v1/reference/snapshot` is the one A2A route, and it sits behind
`require_service_caller`, so it is service-authenticated rather than open. It is the most
sensitive surface in the repo: an MNPI holding list names which employees hold inside
information on which issuers, and a restricted list leaks deal flow. Treat its S2S credential as
a market-abuse control, not an integration detail, and keep the outbound `trade-comms-surveillance` allowlist narrow.

### Where does personal data go?

It is masked before it crosses any boundary, not once at the end. Redaction runs before the
audit write (`domain/assessment_service.py` writes `redacted_summary=redact(...)`), before a
review payload leaves the process (`adapters/_review_payload.py`, against EVERY jurisdiction's
rows because the console is a shared sink), and before a tool result can enter a model's context
(`agent/tools.py`). The pattern set and its ORDER are this vertical's (`domain/pii.py`, national
rows first, universal rows last), drawn from the shared `pii-kit`. The `pii_safety` eval metric
holds this at `>= 0.99` and `tests/unit/test_not_falsely_green.py` proves the metric can go red.

Note the class of data involved: a conflicts register holds staff identities, staff trading
positions and gift counterparties. That is employee personal data plus market-sensitive
position data, so the redaction boundary and the WORM retention decision both need employment
and privacy sign-off, not only a security one.

### Can the model exfiltrate or invent anything?

The model is reachable through exactly one port (`ports/llm.py`) and has two narrow jobs, neither
consequential: resolve a counterparty entity from free text during ingestion, and draft the
rationale for an ALREADY-FIXED verdict. The entity reply is validated against
`COUNTERPARTY_SCHEMA` and DISCARDED on any failure, falling back to the structured
`counterparty` field, so a bad reply changes an enrichment label and never a screening input.
The rationale is checked by `is_grounded` (`domain/assessment_service.py`) and replaced with the
deterministic summary if it invents a figure. Prompt-injection screening through the `agent-guardrail-gateway` is **not** wired yet, so untrusted declaration narratives should be treated as
hostile input until it is (rule R1 in `COMPLIANCE.md`).

### How is the audit trail protected?

Append-only and hash-chained, AND externally anchored. The chain catches an edit, a deletion or a
reorder; only the anchor catches a TRUNCATED TAIL, because dropping the newest rows leaves a
shorter chain that verifies perfectly. `audit_anchor_path` (`CONFLICTSPAD_AUDIT_ANCHOR`) writes
the chain head to a file on another volume, and `tests/unit/test_audit_anchor.py` proves the
detection, proves the control case goes UNDETECTED without an anchor, and proves an append after
truncation refuses rather than re-anchoring. Under the managed profile the sink is a locked
Cloud Logging bucket (`infra/terraform/logging_worm.tf`), which provides non-rewritability
itself.

### What about supply chain?

Both lockfiles are committed and pin every dependency exactly; the catalog commons are pinned to
40-character COMMIT shas rather than tags, because a re-pushed tag changes what installs with no
diff in the lockfile. The base image is digest-pinned, Actions are SHA-pinned, dependabot covers
pip, docker, github-actions and npm, and `pip-audit` plus `npm audit --audit-level=high` are HARD
CI failures. `tests/unit/test_repo_artifacts.py` asserts each of these from inside the repo, and
it asks git whether each pinned sha is a COMMIT object rather than an annotated tag object, which
a regular expression cannot tell apart.

### What is deliberately out of scope?

- **Login.** This repo authenticates nobody itself: the platform in front of it does, and the UI
  forwards the assertion without parsing or trusting a parsed copy.
- **Injection defence and output filtering.** Owned by `agent-guardrail-gateway`; not bound yet.
- **The review queue.** Owned by `human-review-console`; this repo produces escalations and routes them.
- **Trade and communications surveillance.** Owned by `trade-comms-surveillance`. This repo publishes the reference
  snapshot it screens against; it does not watch order flow or chat.
- **Network egress control.** VPC-SC governs access to Google APIs across perimeters, not
  arbitrary internet egress. The private-egress rule that lets this service reach the `human-review-console` and nothing else is an adopter network decision, called out in `COMPLIANCE.md` P-01.
