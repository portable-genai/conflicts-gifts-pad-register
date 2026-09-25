"""GCP LlmPort: Vertex AI text generation (SDK imports stay lazy).

The ``vertexai`` import lives inside the method so the ``local`` / ``onprem`` profiles import this
module with no GCP SDK installed (the portability proof). The model narrates and resolves
entities only; it never produces a screening number or verdict.
"""

from __future__ import annotations

from hex_service_kit import provenance

from ...config import Settings

#: The model this adapter calls. A module constant rather than a literal inside the call: the
#: model pill reads the id off the BINDING, so a model named only at a call site is a
#: model the served UI cannot state. One name, one place, read by both.
_MODEL = "gemini-3.5-flash"


class VertexLlmAdapter:
    """Generate narration / entity resolution via Vertex AI in the residency region."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(
        self,
        prompt: str,
        *,
        schema: dict[str, object] | None = None,
        temperature: float | None = None,
    ) -> str:
        # Lazy import: absent in the offline profile and in CI.
        from vertexai.generative_models import GenerativeModel

        model = GenerativeModel(_MODEL)
        # Free sampling is an ABSENT temperature, not 1.0: only a pinned call site sends one.
        if temperature is None:
            response = model.generate_content(prompt)
        else:
            response = model.generate_content(
                prompt, generation_config={"temperature": temperature}
            )
        provenance.note_model(_MODEL)
        return str(response.text)
