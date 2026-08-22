"""An untagged register record is not world-readable, and it is not writable either (check C2).

The route compared the record's tenant to the verified principal's like this::

    if record.tenant and record.tenant != principal.tenant:

and called itself fail-closed in its own docstring. The leading truthiness is the defect: a
record whose tenant is the empty string skips the comparison entirely, so EVERY tenant passes the
check for it and an untagged row is world-readable. The identity derivation above it is correct
(the request schema carries no tenant and no actor); the authorization then threw that derivation
away for exactly the rows nobody had tagged.

Untagged rows are not hypothetical here. Two producers made them: the agent tool defaulted
``tenant=""``, and a verified IAP principal with no hosted-domain claim resolves to
``tenant=""`` as well, so the API's own assess path wrote one for such a caller.

Two halves, tested here, because either alone leaves the hole open:

* the READ denies a record whose tenant does not EQUAL the principal's, which includes an
  untagged record and a principal with no tenant. It stays a 403 rather than a 404 for the
  reason the route already gives: a caller must not learn which ids exist in another tenant from
  the difference.
* the WRITE refuses an untagged record in the first place, in every store family, so the read
  guard is a second line rather than the only one.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from hex_service_kit.identity import Principal

from conflicts_gifts_pad_register.config import build_container
from conflicts_gifts_pad_register.domain.errors import RegisterError
from conflicts_gifts_pad_register.domain.models import ConflictAssessment

from tests.conftest import LOOPBACK_PEER, local_settings
from tests.fixtures import sample_cases

#: A record with no tenant tag: what the agent tool's old default wrote, and what a store shared
#: with another writer can still hand back.
UNTAGGED_RECORD: ConflictAssessment = dataclasses.replace(
    sample_cases.CANONICAL_ASSESSMENT, declaration_id="dec-untagged", tenant=""
)

#: A verified principal carrying no tenant: exactly what the IAP adapter resolves for a token
#: with no hosted-domain claim (see ``tests/unit/test_iap_identity.py``).
TENANTLESS_PRINCIPAL = Principal(
    subject="nobody@gmail.example", principals=("group:analyst",), tenant=""
)


def _body(declaration_id: str = "dec-tenantless") -> dict[str, object]:
    declaration = sample_cases.FLAGGED_DECLARATION
    return {
        "id": declaration_id,
        "employee": declaration.employee,
        "employee_role": declaration.employee_role,
        "market": declaration.market,
        "kind": declaration.kind.value,
        "description": declaration.description,
        "as_of": declaration.as_of,
        "counterparty": declaration.counterparty,
        "amount_minor": declaration.amount_minor,
        "currency": declaration.currency,
    }


@pytest.fixture()
def app_and_client() -> Iterator[tuple[object, TestClient]]:
    """The real app object plus a loopback client, so the module can override its dependencies.

    The app's container is an ``lru_cache`` of one, and an earlier test in the suite can leave a
    container built under a different profile in it. Clearing it on both sides pins these tests
    to the profile the gate runs under rather than to the file order.
    """
    from conflicts_gifts_pad_register.api.app import _container, app

    _container.cache_clear()
    try:
        with TestClient(app, client=LOOPBACK_PEER) as client:
            yield app, client
    finally:
        _container.cache_clear()


def test_an_untagged_record_is_not_readable_by_an_unrelated_tenant(
    app_and_client: tuple[object, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store hands over the row; the route must refuse to serve it."""
    from conflicts_gifts_pad_register.api.app import _container

    app, client = app_and_client
    store = _container().register_store
    monkeypatch.setattr(store, "get", lambda _id: UNTAGGED_RECORD)

    resp = client.get("/v1/register/dec-untagged", headers={"X-Dev-Persona": "other-tenant"})
    assert resp.status_code == 403, (
        "an untagged record was served across the tenant boundary: the truthiness in the "
        f"comparison made it world-readable (got {resp.status_code})"
    )


def test_an_untagged_record_is_not_readable_by_a_principal_with_no_tenant(
    app_and_client: tuple[object, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two empty strings are not a match: neither side names a tenant, so neither authorizes."""
    from conflicts_gifts_pad_register.api.app import _container, get_principal

    app, client = app_and_client
    store = _container().register_store
    monkeypatch.setattr(store, "get", lambda _id: UNTAGGED_RECORD)
    app.dependency_overrides[get_principal] = lambda: TENANTLESS_PRINCIPAL  # type: ignore[attr-defined]
    try:
        resp = client.get("/v1/register/dec-untagged")
    finally:
        app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert resp.status_code == 403, (
        f"an empty principal tenant matched an empty record tenant (got {resp.status_code})"
    )


def test_the_assess_path_refuses_to_file_a_record_for_a_principal_with_no_tenant(
    app_and_client: tuple[object, TestClient],
) -> None:
    """Where the untagged rows came from: refuse at the WRITE, not only at the read."""
    from conflicts_gifts_pad_register.api.app import _container, get_principal

    app, client = app_and_client
    app.dependency_overrides[get_principal] = lambda: TENANTLESS_PRINCIPAL  # type: ignore[attr-defined]
    try:
        resp = client.post("/v1/assess", json=_body())
    finally:
        app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert resp.status_code == 403, (
        f"an untagged register record was filed and returned (got {resp.status_code})"
    )
    assert _container().register_store.get("dec-tenantless") is None, (
        "the untagged record reached the store anyway"
    )


@pytest.mark.parametrize("profile", ["local", "gcp", "onprem"])
def test_every_register_store_family_refuses_an_untagged_write(profile: str) -> None:
    """The refusal runs BEFORE the adapter's own body, so no family can be the one that forgets.

    ``gcp`` and ``onprem`` refuse everything offline anyway, but with their own error types; this
    asserts the DOMAIN error, which is only raised if the tenant guard runs first.
    """
    store = build_container(local_settings(profile=profile)).register_store
    with pytest.raises(RegisterError):
        store.put(UNTAGGED_RECORD)
