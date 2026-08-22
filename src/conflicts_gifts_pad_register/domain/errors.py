"""Domain exceptions for the conflicts / gifts / PAD register (pure Python, no SDK).

The domain layer never imports a cloud SDK or a web framework, so these let callers (API, CLI,
the agent surface) react to domain-level failures without coupling to a vendor error type.
"""

from __future__ import annotations


class RegisterError(Exception):
    """Base class for all domain-level errors this service raises."""


class ScreeningPackError(RegisterError):
    """Raised when the screening threshold pack is missing or malformed.

    Fail-closed: screening is only as good as its thresholds, so an unreadable or invalid pack
    is a hard error rather than a silently empty rule set that would wave every gift through.
    """


class TenantAccessDeniedError(RegisterError):
    """Raised when a principal asks for a register record owned by another tenant (HTTP 403).

    The check lives in the domain so every driving adapter inherits it, and it is a DENIAL
    (403), never a not-found (404): a caller must not be able to probe which ids exist in
    another tenant by the difference between the two.

    "Owned by another tenant" includes owned by NOBODY. See
    :func:`~conflicts_gifts_pad_register.domain.tenancy.authorize_tenant_read`.
    """


class UntaggedRegisterRecordError(RegisterError):
    """Raised when a register write carries no tenant tag (HTTP 403 on a driving surface).

    Tenant isolation on this data is a data TAG, so a record with an empty tag has no owner and
    no read of it can ever be authorized honestly. Refusing the write is the half that keeps the
    read guard a second line of defence rather than the only one: a row nobody can be shown
    should not be in the store waiting for the next comparison to be written slightly wrong.
    """
