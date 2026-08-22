"""IngestionService: deterministic normalisation with model-assisted entity resolution.

The split the whole service turns on: DETERMINISTIC code owns the amount, the effective date and
the instrument identity (anything a screening decision consumes), and the MODEL only resolves the
counterparty entity from free text. The model's answer is validated against a schema and DISCARDED
on any failure, falling back to the structured ``counterparty`` field, so a bad or malformed model
response can never change a consequential input, only the enrichment label.

Pure domain code: it takes the :class:`~conflicts_gifts_pad_register.ports.llm.LlmPort` by
constructor injection and imports no SDK.
"""

from __future__ import annotations

import json
from typing import Any

from ..ports.llm import LlmPort
from .models import Declaration, Instrument, NormalizedDeclaration

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

    def __init__(self, llm: LlmPort) -> None:
        self._llm = llm

    def normalize(self, declaration: Declaration) -> NormalizedDeclaration:
        instrument = self._normalize_instrument(declaration.instrument)
        counterparty, resolved = self._resolve_counterparty(declaration)
        return NormalizedDeclaration(
            declaration=declaration,
            counterparty_entity=counterparty,
            # Deterministic: the amount is an integer of minor units and passes through unchanged.
            amount_minor=int(declaration.amount_minor),
            instrument=instrument,
            model_resolved=resolved,
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
    def _resolve_counterparty(self, declaration: Declaration) -> tuple[str, bool]:
        """Return ``(counterparty, model_resolved)``; fall back to the structured field on failure.

        The deterministic fallback is the ``counterparty`` field as ingested, so a discarded
        model reply degrades to the structured value rather than to nothing.
        """
        fallback = declaration.counterparty.strip()
        prompt = self._prompt(declaration)
        try:
            raw = self._llm.generate(prompt, schema=COUNTERPARTY_SCHEMA)
        except Exception:
            return fallback, False
        resolved = self._parse(raw)
        if resolved is None:
            return fallback, False
        return resolved, True

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
