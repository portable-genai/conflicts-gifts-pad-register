"""GCP RegisterStorePort: Firestore assessment store (SDK imports stay lazy).

The managed register store reads and writes conflict assessments in Firestore in the residency
region, tenant-scoped on the listing path exactly like the offline adapter. The SDK import is
lazy, so the offline profiles import this module with no GCP SDK installed.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ConflictAssessment
from ...domain.tenancy import require_tenant_tag


class FirestoreRegisterStore:
    """Read and write conflict assessments in Firestore."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_for_employee(  # pragma: no cover - needs live GCP
        self, tenant: str, employee: str
    ) -> tuple[ConflictAssessment, ...]:
        from google.cloud import firestore

        _ = firestore.Client()
        raise RuntimeError("Firestore register query is a deployment binding")

    def get(self, assessment_id: str) -> ConflictAssessment | None:  # pragma: no cover - live GCP
        from google.cloud import firestore

        _ = firestore.Client()
        raise RuntimeError("Firestore register get is a deployment binding")

    def put(self, assessment: ConflictAssessment) -> str:
        # Before the SDK import, so an untagged record is refused by the DOMAIN rule on every
        # profile rather than only where a Firestore client happens to be constructible. The
        # rest of the body still needs live GCP.
        require_tenant_tag(assessment.tenant)

        from google.cloud import firestore  # pragma: no cover - needs live GCP

        _ = firestore.Client()  # pragma: no cover - needs live GCP
        raise RuntimeError(  # pragma: no cover - needs live GCP
            "Firestore register put is a deployment binding"
        )
