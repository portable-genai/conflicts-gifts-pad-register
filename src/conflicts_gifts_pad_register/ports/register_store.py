"""RegisterStorePort: the tenant-scoped store of conflict assessments (the register itself).

The register is tenant-owned data, so the two read methods differ deliberately, exactly like the
reference evidence store in the fleet:

* :meth:`list_for_employee` takes the tenant and MUST filter on it in the store, so a query can
  never span tenants, and
* :meth:`get` is a raw fetch by id that does NOT filter: the caller (the API, via the domain)
  compares the record's tenant to the VERIFIED principal's tenant and denies with
  :class:`~conflicts_gifts_pad_register.domain.errors.TenantAccessDeniedError` (HTTP 403).
  Keeping the check in the domain means every driving adapter inherits it, and an adapter cannot
  become the only place the boundary is enforced.

:meth:`put` refuses a record whose tenant tag is EMPTY, in every family, by calling
:func:`~conflicts_gifts_pad_register.domain.tenancy.require_tenant_tag` before it does anything
else. A row with no owner is a row no read can authorize honestly, and while the route's
comparison skipped untagged rows, every tenant could read them.

Never pass a client-supplied tenant into either method: the tenant comes from the verified
principal the IdentityPort resolved. The ``local`` adapter is an SDK-free SQLite store; the
``gcp`` adapter is Firestore in the residency region; the ``onprem`` adapter fails fast.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ConflictAssessment


@runtime_checkable
class RegisterStorePort(Protocol):
    def list_for_employee(self, tenant: str, employee: str) -> tuple[ConflictAssessment, ...]:
        """Return the assessments ``tenant`` holds for ``employee`` (store-side tenant filter)."""
        ...

    def get(self, assessment_id: str) -> ConflictAssessment | None:
        """Return one assessment by id, or ``None``; the DOMAIN authorizes the tenant."""
        ...

    def put(self, assessment: ConflictAssessment) -> str:
        """Upsert one assessment and return its id; an UNTAGGED record is refused."""
        ...
