"""One guardrail screen, reduced to "the text to use" or "a refusal to audit" (rule R1).

Both generation calls this service makes are enrichment over a decision the deterministic engine
owns: counterparty resolution falls back to the structured ``counterparty`` field, and narration
falls back to the deterministic summary. So a refused screen does not fail the assessment; it
discards the model step and returns a :class:`~.kernel.GuardrailRefusal` the orchestrator audits
``Decision.BLOCKED``. Nothing a refused screen saw is used, and nothing partial is returned.

FAIL CLOSED: a verdict is usable only when it is allowed AND carries ``sanitized_text``, and that
text is used from then on EXACTLY as given (an empty string included), never the unscreened
original. A guardrail that raises instead of deciding (its backend errored or timed out, or the
on-prem placeholder is bound) is a refusal like any block: the model step is skipped, and the
refusal says the guardrail was unavailable.
"""

from __future__ import annotations

from ..ports.guardrail import GuardrailPort
from .kernel import Direction, GuardrailRefusal


def screen_text(
    guardrail: GuardrailPort, text: str, direction: Direction, *, step: str
) -> str | GuardrailRefusal:
    """Return the screened text to use, or the refusal that replaces it."""
    try:
        verdict = guardrail.screen(text, direction)
    except Exception as exc:
        return GuardrailRefusal(
            step=step,
            direction=direction,
            reason=f"guardrail unavailable ({type(exc).__name__})",
        )
    if not verdict.allowed or verdict.sanitized_text is None:
        return GuardrailRefusal(
            step=step,
            direction=direction,
            reason=verdict.reason or f"{step} {direction.value} blocked by guardrail",
        )
    return verdict.sanitized_text
