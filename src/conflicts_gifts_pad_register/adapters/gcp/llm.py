"""GCP LlmPort: Vertex AI text generation (SDK imports stay lazy).

The ``vertexai`` import lives inside the method so the ``local`` / ``onprem`` profiles import this
module with no GCP SDK installed (the portability proof). The model narrates and resolves
entities only; it never produces a screening number or verdict.
"""

from __future__ import annotations

from ...config import Settings


class VertexLlmAdapter:
    """Generate narration / entity resolution via Vertex AI in the residency region."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(  # pragma: no cover - needs live GCP
        self, prompt: str, *, schema: dict[str, object] | None = None
    ) -> str:
        # Lazy import: absent in the offline profile and in CI.
        from vertexai.generative_models import GenerativeModel

        model = GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return str(response.text)
