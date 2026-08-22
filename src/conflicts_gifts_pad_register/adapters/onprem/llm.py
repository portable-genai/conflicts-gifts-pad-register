"""On-prem LlmPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings


class OnPremLlmAdapter:
    """Satisfies LlmPort but refuses: the client binds its own on-premises model gateway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        raise NotImplementedError(
            "on-prem model gateway is a portability placeholder: bind the client's own hosted "
            "model (see docs/onprem-migration.md). Screening does not depend on it; narration does."
        )
