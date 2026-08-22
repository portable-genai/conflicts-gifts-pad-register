"""The one definition of tenant isolation for the register (pure stdlib, no SDK, no framework).

Object-level authorization on this data is a DATA TAG comparison, and it lives here rather than
in a route so that every driving surface inherits the same answer and no adapter can become the
only place the boundary is enforced (see ``ports/register_store.py``).

Both halves are here because either alone leaves the hole open:

* :func:`authorize_tenant_read` decides whether a stored record may be served to a principal, and
* :func:`require_tenant_tag` refuses to let an untagged record be stored at all.

The rule both express is EQUALITY between two identified tenants. It is written that way because
the route used to write it as ``record.tenant and record.tenant != principal.tenant``, and the
leading truthiness made an untagged record world-readable: the comparison was skipped for it, so
every principal passed. An empty string is not a tenant that matches everything; it is the
absence of a tenant, and the absence of a tenant authorizes nobody.
"""

from __future__ import annotations

from .errors import TenantAccessDeniedError, UntaggedRegisterRecordError


def authorize_tenant_read(*, record_tenant: str, principal_tenant: str) -> None:
    """Allow the read only when both sides name a tenant AND the two are equal.

    Three ways to be denied, and the first two are the ones a truthiness check waved through:

    * the record carries no tenant tag, so nobody owns it and nobody may read it;
    * the principal carries no tenant (a verified IAP token with no hosted-domain claim resolves
      to exactly that), so it cannot be the owner of anything;
    * the two are both present and different.

    Raises :class:`~conflicts_gifts_pad_register.domain.errors.TenantAccessDeniedError`, which a
    driving surface answers as 403 and never as 404: a caller must not learn which ids exist in
    another tenant from the difference between the two.

    The message names no tenant: the denial is the caller's answer, and which partition the
    record actually belongs to is not the caller's business.
    """
    if not record_tenant or not principal_tenant or record_tenant != principal_tenant:
        raise TenantAccessDeniedError("assessment belongs to another tenant")


def require_tenant_tag(tenant: str) -> None:
    """Refuse a register write whose record carries no tenant tag.

    Called by every :class:`~conflicts_gifts_pad_register.ports.register_store.RegisterStorePort`
    implementation BEFORE it does anything else, so an untagged record cannot enter any store,
    managed or offline. Two producers used to make them: the agent tool defaulted to an empty
    tenant, and the API filed a record for a verified principal that carried none.

    Raises :class:`~conflicts_gifts_pad_register.domain.errors.UntaggedRegisterRecordError`.
    """
    if not tenant:
        raise UntaggedRegisterRecordError(
            "a register record must carry a tenant tag: an untagged record has no owner, so no "
            "read of it could ever be authorized"
        )
