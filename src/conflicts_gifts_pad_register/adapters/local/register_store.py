"""Local RegisterStorePort: an SDK-free, in-memory, tenant-scoped assessment store.

The offline stand-in for the managed register (Firestore on GCP). Tenant isolation is enforced
in the LISTING: :meth:`list_for_employee` filters on ``tenant``, so a listing can never span
tenants. :meth:`get` is deliberately an unfiltered fetch by id, because the domain (the API
route) is where the fail-closed comparison against the verified principal's tenant happens and
returns a 403. That split is what makes the cross-tenant denial test meaningful: the store hands
over the record, and the domain refuses to serve it.

:meth:`put` refuses a record with no tenant tag (``domain/tenancy.py``). An untagged row has no
owner, so no read of it can be authorized honestly, and while the route's comparison skipped
untagged rows every tenant could read them. The write refusal is why that read guard is now a
second line of defence rather than the only one.
"""

from __future__ import annotations

import threading

from ...config import Settings
from ...domain.models import ConflictAssessment
from ...domain.tenancy import require_tenant_tag


class LocalRegisterStore:
    """Hold conflict assessments in memory, tenant-scoped on the listing path."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        self._by_id: dict[str, ConflictAssessment] = {}

    def list_for_employee(self, tenant: str, employee: str) -> tuple[ConflictAssessment, ...]:
        if not tenant:
            # Fail closed: an unresolved tenant reads nothing rather than everything.
            return ()
        with self._lock:
            found = [
                a for a in self._by_id.values() if a.tenant == tenant and a.employee == employee
            ]
        return tuple(sorted(found, key=lambda a: a.declaration_id))

    def get(self, assessment_id: str) -> ConflictAssessment | None:
        with self._lock:
            return self._by_id.get(assessment_id)

    def put(self, assessment: ConflictAssessment) -> str:
        require_tenant_tag(assessment.tenant)
        with self._lock:
            self._by_id[assessment.declaration_id] = assessment
        return assessment.declaration_id
