"""On-prem RegisterStorePort: fail-fast portability placeholder (sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ConflictAssessment
from ...domain.tenancy import require_tenant_tag

_MESSAGE = (
    "on-prem register store is a portability placeholder: bind the client's own conflicts "
    "register (see docs/onprem-migration.md)"
)


class OnPremRegisterStore:
    """Satisfies RegisterStorePort but refuses: the client binds its own register of record."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_for_employee(self, tenant: str, employee: str) -> tuple[ConflictAssessment, ...]:
        raise NotImplementedError(_MESSAGE)

    def get(self, assessment_id: str) -> ConflictAssessment | None:
        raise NotImplementedError(_MESSAGE)

    def put(self, assessment: ConflictAssessment) -> str:
        # The tenant rule is the DOMAIN's, so it holds even on the family that binds nothing: a
        # client wiring its own register here inherits the refusal rather than reinventing it.
        require_tenant_tag(assessment.tenant)
        raise NotImplementedError(_MESSAGE)
