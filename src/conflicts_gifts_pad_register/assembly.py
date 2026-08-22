"""Assembly helpers: build the domain services from a bound container.

Lives outside ``domain/`` because it depends on the container and the pack loader (both do I/O
or importlib), while the domain services stay pure and take their ports by constructor injection.
Every driving surface (API, CLI, agent, demo, eval) builds the assessment service the same way
through here, so the wiring lives in one place rather than being retyped per surface.
"""

from __future__ import annotations

from .config import Container, Settings, build_container
from .domain.assessment_service import AssessmentService
from .domain.ingestion_service import IngestionService
from .screening_pack import pack_for


def build_assessment_service(container: Container) -> AssessmentService:
    """Wire the ingestion and screening pipeline over the container's bound ports."""
    ingestion = IngestionService(container.llm)
    pack = pack_for(container.settings.screening_pack_path)
    return AssessmentService(
        ingestion=ingestion,
        reference_store=container.reference_store,
        audit=container.audit,
        llm=container.llm,
        pack=pack,
        tracer=container.tracer,
    )


def assessment_service(settings: Settings | None = None) -> tuple[Container, AssessmentService]:
    """Build a container and its assessment service in one call (the common surface need)."""
    container = build_container(settings)
    return container, build_assessment_service(container)
