"""LlmPort: the boundary to a narrating / entity-resolving language model.

The model has exactly two narrow jobs in this service, and neither is consequential:

* resolve a counterparty entity from a free-text declaration (``ingestion_service.py``), under
  schema validation with a deterministic fallback, and
* draft the cited rationale for an ALREADY-FIXED approve / escalate verdict
  (``assessment_service.py``), restating engine findings only.

It never produces a number, a severity or a verdict. The ``local`` adapter is deterministic and
SDK-free (so the gate and the demo run offline), the ``gcp`` adapter calls Vertex with a lazy
import, and the ``onprem`` adapter fails fast.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmPort(Protocol):
    def generate(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        """Return the model's completion for ``prompt`` (JSON text when ``schema`` is given)."""
        ...
