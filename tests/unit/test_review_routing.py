"""Rule R8: a flagged assessment is ROUTED to human-review-console, not left in a per-repo boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
a flagged assessment produces an outbound review, a cleared one produces none, the payload leaves
redacted, and the on-prem placeholder refuses rather than swallowing the escalation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conflicts_gifts_pad_register.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from conflicts_gifts_pad_register.adapters.local.review_router import (
    LocalReviewRouter,
)
from conflicts_gifts_pad_register.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from conflicts_gifts_pad_register.api.app import (
    app,
)
from conflicts_gifts_pad_register.assembly import (
    build_assessment_service,
)
from conflicts_gifts_pad_register.config import (
    Settings,
    build_container,
)
from conflicts_gifts_pad_register.domain.kernel import (
    Severity,
)
from conflicts_gifts_pad_register.domain.models import (
    ConflictAssessment,
    Declaration,
    DeclarationKind,
    Instrument,
)

from tests.fixtures import sample_cases

_ACTOR = "analyst@bank.example"

#: A personal-account deal on the MNPI symbol by the insider: the CRITICAL, dual-control case.
_MNPI_PAD = Declaration(
    id="pad-mnpi",
    tenant="demo-bank",
    employee="chen.trader@bank.example",
    employee_role="trader",
    market="SG",
    kind=DeclarationKind.PERSONAL_ACCOUNT_DEAL,
    description="Buy 50 ORBX via personal broker account.",
    as_of=sample_cases.AS_OF,
    amount_minor=800000,
    currency="SGD",
    instrument=Instrument(symbol="ORBX", name="Orbit Example Corp (FICTIONAL)"),
)


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant="demo-bank")


def _assess(declaration: Declaration) -> ConflictAssessment:
    service = build_assessment_service(build_container(_settings()))
    return service.assess(declaration, actor=_ACTOR)


def test_a_flagged_assessment_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    ref = router.route(_assess(sample_cases.FLAGGED_DECLARATION), maker=_ACTOR)
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == _ACTOR
    assert review.tenant == "demo-bank"
    assert review.severity == Severity.HIGH.value
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_a_critical_assessment_demands_dual_control() -> None:
    router = LocalReviewRouter(_settings())
    router.route(_assess(_MNPI_PAD), maker=_ACTOR)
    assert router.outbox.pending()[0].review.required_approvals == 2


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """human-review-console is a shared sink; the employee identifier must never reach the wire in
    the clear.
    """
    router = LocalReviewRouter(_settings())
    router.route(_assess(sample_cases.FLAGGED_DECLARATION), maker=_ACTOR)
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert sample_cases.FLAGGED_DECLARATION.employee not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """An escalation with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(_assess(sample_cases.FLAGGED_DECLARATION), maker=_ACTOR)


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(sample_cases.CANONICAL_ASSESSMENT, maker=_ACTOR)


def _body(declaration: Declaration) -> dict[str, object]:
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


def test_the_api_routes_the_escalation_in_the_same_request() -> None:
    """The serving path, not just the adapter: an escalation must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    escalated = client.post(
        "/v1/assess",
        json=_body(sample_cases.FLAGGED_DECLARATION),
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert escalated["requires_human_review"] is True
    assert escalated["review_ref"], "an escalation with no routing reference went nowhere"

    routine = client.post(
        "/v1/assess",
        json=_body(sample_cases.CLEAN_DECLARATION),
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert routine["requires_human_review"] is False
    assert routine["review_ref"] == "", "a cleared assessment must not manufacture a review"
