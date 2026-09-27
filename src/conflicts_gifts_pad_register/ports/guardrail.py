"""GuardrailPort: the boundary that screens a generation call in both directions (rule R1).

Rule R1 is the reason this port exists: a service that binds ``agent-guardrail-gateway`` as a
mandatory dependency must screen every inbound prompt BEFORE it reaches a model, and every
outbound answer AFTER it is produced and BEFORE anything downstream uses it. This service has
two such calls, both narration/enrichment only, never the consequential decision:

* ``domain/ingestion_service.py`` resolves the counterparty entity from free declaration text;
* ``domain/assessment_service.py`` drafts the cited rationale over an ALREADY-FIXED verdict.

Both call sites screen the prompt they are about to send (INPUT) and the text the model
returned (OUTPUT) before using it, through ``domain/guardrail_screen.py``. Because neither call
may ever change a consequential input, a refusal discards that model step and uses the
deterministic fallback, and the orchestrator audits the refusal ``Decision.BLOCKED``.

The domain stays pure. This port names the screen; the adapters (not this module) depend on the
managed guardrail service (Model Armor) or a local heuristic stand-in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.kernel import Direction, GuardrailVerdict


@runtime_checkable
class GuardrailPort(Protocol):
    def screen(self, text: str, direction: Direction) -> GuardrailVerdict:
        """Screen inbound prompt or outbound response text; may sanitise it.

        Never raises on a policy match: a block is reported as ``GuardrailVerdict(allowed=False,
        ...)`` so the caller can audit the attempt before deciding how to fail. An allowed verdict
        carries ``sanitized_text``, the text the caller uses from then on EXACTLY as given (the
        input unchanged when nothing was redacted, possibly empty when everything was); the
        caller never falls back to the unscreened original.

        Raising is reserved for the adapter being unable to decide at all: its backend errored
        or timed out, no template is configured, or the on-prem placeholder is bound. The domain
        treats every such raise as a refusal (fail closed): the model step is skipped, and the
        refusal is audited like a block.
        """
        ...
