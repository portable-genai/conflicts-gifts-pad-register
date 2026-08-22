"""Local LlmPort: a deterministic, SDK-free narrating model for the offline profile.

No network, no cloud SDK, and the SAME output every time, which is what lets the gate and the
demo run offline and replayably. It answers the two prompt shapes the domain sends:

* an entity-resolution prompt (schema wants ``counterparty``): it extracts the first fictional
  entity named in the declaration text, so a real declaration's counterparty is resolved without
  a model, and returns empty when it finds none so ingestion falls back to the structured field;
* a rationale prompt (schema wants ``rationale``): it echoes the deterministic BASELINE the
  service already computed from the engine's findings, so the narration is grounded by
  construction and never invents a figure.

Because it only ever restates what it was given, it cannot produce a number the engine did not,
which is the whole point of keeping the model on a short leash.
"""

from __future__ import annotations

import json
import re

from ...config import Settings

_ENTITY = re.compile(r"([A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+)*) \(FICTIONAL\)")


class LocalLlmAdapter:
    """A deterministic offline stand-in for the narrating model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        required = (schema or {}).get("required", [])
        wants = set(required) if isinstance(required, list) else set()
        if "rationale" in wants:
            return json.dumps({"rationale": self._baseline(prompt)})
        if "counterparty" in wants:
            entity = self._entity(prompt)
            return json.dumps({"counterparty": entity, "entities": [entity] if entity else []})
        # No known schema: reflect nothing rather than fabricate.
        return json.dumps({})

    @staticmethod
    def _baseline(prompt: str) -> str:
        marker = "BASELINE:"
        if marker in prompt:
            tail = prompt.split(marker, 1)[1]
            return tail.split("\n\n", 1)[0].strip()
        return ""

    @staticmethod
    def _entity(prompt: str) -> str:
        match = _ENTITY.search(prompt)
        return f"{match.group(1)} (FICTIONAL)" if match else ""
