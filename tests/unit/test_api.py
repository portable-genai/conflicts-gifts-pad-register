"""API surface: verified-principal identity, tenant-scoped register, fail-closed S2S.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from conflicts_gifts_pad_register.domain.models import Declaration

from tests.fixtures import sample_cases

_TOKEN_ENV = "CONFLICTSPAD_S2S_TOKEN"


def _body(declaration: Declaration = sample_cases.FLAGGED_DECLARATION) -> dict[str, object]:
    body: dict[str, object] = {
        "id": declaration.id,
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
    if declaration.instrument is not None:
        body["instrument"] = {"symbol": declaration.instrument.symbol}
    return body


def test_assess_uses_the_verified_principal_and_flags_deterministically(
    api_client: TestClient,
) -> None:
    resp = api_client.post(
        "/v1/assess",
        json=_body(),
        headers={"X-Dev-Persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "high"
    assert body["verdict"] == "escalate"
    assert body["requires_human_review"] is True
    # Rule R8: the escalation was routed, not merely flagged (see test_review_routing.py).
    assert body["review_ref"]
    assert any(f["rule_id"] == "gift_threshold" for f in body["findings"])


def test_the_register_denies_a_cross_tenant_read(api_client: TestClient) -> None:
    """The store fetch is unfiltered; the fail-closed tenant comparison lives in the API."""
    created = api_client.post(
        "/v1/assess",
        json=_body(),
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assessment_id = created["declaration_id"]

    same_tenant = api_client.get(
        f"/v1/register/{assessment_id}",
        headers={"X-Dev-Persona": "auditor"},
    )
    assert same_tenant.status_code == 200

    other_tenant = api_client.get(
        f"/v1/register/{assessment_id}",
        headers={"X-Dev-Persona": "other-tenant"},
    )
    assert other_tenant.status_code == 403, "a record must not cross the tenant boundary"


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/assess",
        json=_body(sample_cases.CLEAN_DECLARATION),
        headers={"X-Dev-Persona": "ghost"},
    )
    assert resp.status_code == 401


def test_the_reference_feed_serves_the_as_of_snapshot_cmp1_reads(api_client: TestClient) -> None:
    """The A2A snapshot: an S2S feed (open on the loopback local posture) replayable at as_of."""
    resp = api_client.get("/v1/reference/snapshot", params={"as_of": sample_cases.AS_OF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == sample_cases.AS_OF
    assert any(entry["symbol"] == "FICT" for entry in body["restricted"])


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
