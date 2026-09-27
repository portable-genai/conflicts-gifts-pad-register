"""IngestionService: deterministic normalisation with model-assisted entity resolution.

The split the whole service turns on: DETERMINISTIC code owns the amount, the effective date and
the instrument identity (anything a screening decision consumes), and the MODEL only resolves the
counterparty entity from free text. The model's answer is validated against a schema and DISCARDED
on any failure, falling back to the structured ``counterparty`` field, so a bad or malformed model
response can never change a consequential input, only the enrichment label.

Rule R1: the guardrail screens BOTH directions of the one generation call this service makes.
The declaration text is screened INPUT before it is ever sent to the model, and the model's raw
reply is screened OUTPUT before it is parsed; the model receives, and the parser reads, exactly
the text each screen handed back. A refused direction (a block, or a guardrail that could not
decide) discards the model step and uses the deterministic fallback, the structured
``counterparty`` field, because this call may never change a consequential input, only the
enrichment label. The refusal is carried on the result
(:attr:`~.models.NormalizedDeclaration.guardrail_refusals`) and the orchestrator audits it
``Decision.BLOCKED``, so a refused call is recorded without failing the whole assessment.

Pure domain code: it takes the :class:`~conflicts_gifts_pad_register.ports.llm.LlmPort` and the
:class:`~conflicts_gifts_pad_register.ports.guardrail.GuardrailPort` by constructor injection and
imports no SDK.
"""

from __future__ import annotations

import json
from typing import Any

from ..ports.guardrail import GuardrailPort
from ..ports.llm import LlmPort
from .guardrail_screen import screen_text
from .kernel import Direction, GuardrailRefusal
from .models import Declaration, Instrument, NormalizedDeclaration

#: The step name a refusal of the counterparty-resolution call is audited under.
RESOLVE_STEP = "counterparty resolution"

#: The schema the model's entity-resolution reply must satisfy. A reply that is not an object,
#: or whose ``counterparty`` is not a non-empty string, is discarded.
COUNTERPARTY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "counterparty": {"type": "string"},
        "entities": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["counterparty"],
}


class IngestionService:
    """Normalise a raw declaration into a screenable one; the model only names the counterparty."""

    def __init__(self, llm: LlmPort, guardrail: GuardrailPort) -> None:
        self._llm = llm
        self._guardrail = guardrail

    def normalize(self, declaration: Declaration) -> NormalizedDeclaration:
        instrument = self._normalize_instrument(declaration.instrument)
        counterparty, resolved, refusals = self._resolve_counterparty(declaration)
        return NormalizedDeclaration(
            declaration=declaration,
            counterparty_entity=counterparty,
            # Deterministic: the amount is an integer of minor units and passes through unchanged.
            amount_minor=int(declaration.amount_minor),
            instrument=instrument,
            model_resolved=resolved,
            guardrail_refusals=refusals,
        )

    # ------------------------------------------------------------------ #
    # Deterministic normalisation (owns everything a decision consumes)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_instrument(instrument: Instrument | None) -> Instrument | None:
        if instrument is None:
            return None
        return Instrument(
            symbol=instrument.identity,
            name=instrument.name.strip(),
            isin=instrument.isin.strip().upper(),
        )

    # ------------------------------------------------------------------ #
    # Model-assisted entity resolution (enrichment only, schema-validated)
    # ------------------------------------------------------------------ #
    def _resolve_counterparty(
        self, declaration: Declaration
    ) -> tuple[str, bool, tuple[GuardrailRefusal, ...]]:
        """Return ``(counterparty, model_resolved, refusals)``; fall back on any failure.

        The deterministic fallback is the ``counterparty`` field as ingested, so a discarded
        model reply degrades to the structured value rather than to nothing. Rule R1: the
        prompt is screened INPUT before the call and the raw reply OUTPUT before it is parsed;
        a refused direction degrades to the same fallback and is returned for auditing.
        """
        fallback = declaration.counterparty.strip()
        prompt = screen_text(
            self._guardrail, self._prompt(declaration), Direction.INPUT, step=RESOLVE_STEP
        )
        if isinstance(prompt, GuardrailRefusal):
            return fallback, False, (prompt,)
        try:
            # Extraction: the resolved entity is compared against the register, so it is PINNED.
            raw = self._llm.generate(prompt, schema=COUNTERPARTY_SCHEMA, temperature=0.0)
        except Exception:
            return fallback, False, ()
        reply = screen_text(self._guardrail, raw, Direction.OUTPUT, step=RESOLVE_STEP)
        if isinstance(reply, GuardrailRefusal):
            return fallback, False, (reply,)
        resolved = self._parse(reply)
        if resolved is None:
            return fallback, False, ()
        return resolved, True, ()

    @staticmethod
    def _prompt(declaration: Declaration) -> str:
        return (
            "Read the declaration text and identify the counterparty entity (the giver, host, "
            "outside body or broker). Reply with a JSON object of the form "
            '{"counterparty": "<name>", "entities": ["<name>", ...]}. Do not invent amounts, '
            "dates or instrument codes.\n\nDECLARATION:\n" + declaration.description
        )

    @staticmethod
    def _parse(raw: str) -> str | None:
        """Validate the reply against the schema; return the counterparty, or None to discard."""
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None
        counterparty = obj.get("counterparty")
        if not isinstance(counterparty, str) or not counterparty.strip():
            return None
        return counterparty.strip()
