"""Assessing a declaration opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit store.
So the value of tracing the assessment path depends entirely on the span carrying structural
attributes only: which action, whose, which tenant, which market, which declaration kind. An
employee, a counterparty, a declaration id or a description fragment reaching a span has left
the boundary the service's ``redact`` call exists to hold, and it has left it silently.

The content case drives the declaration whose description carries a planted NRIC, so the check
runs against input that would actually leak if any attribute were content-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from conflicts_gifts_pad_register.config import build_container
from conflicts_gifts_pad_register.domain.assessment_service import AssessmentService
from conflicts_gifts_pad_register.domain.ingestion_service import IngestionService
from conflicts_gifts_pad_register.domain.models import ConflictAssessment, Declaration
from conflicts_gifts_pad_register.screening_pack import pack_for

from tests.conftest import local_settings
from tests.fixtures import sample_cases

#: Every attribute key the assess span is allowed to carry. A flag that started explaining
#: itself on the span (a finding, an employee, a counterparty) would widen this set, which is
#: the point of asserting on the set rather than on the individual keys.
_ASSESS_KEYS = {"action", "actor", "tenant", "market", "kind"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _assess(declaration: Declaration) -> tuple[_RecordingTracer, ConflictAssessment]:
    """The REAL local adapters, exactly as ``assembly.build_assessment_service`` wires them."""
    container = build_container(local_settings())
    tracer = _RecordingTracer()
    service = AssessmentService(
        ingestion=IngestionService(container.llm),
        reference_store=container.reference_store,
        audit=container.audit,
        llm=container.llm,
        pack=pack_for(container.settings.screening_pack_path),
        tracer=tracer,  # type: ignore[arg-type]
    )
    result = service.assess(declaration, actor=sample_cases.ACTOR)
    return tracer, result


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute VALUE that was emitted, and every KEY, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_assessing_a_declaration_opens_exactly_one_named_span() -> None:
    tracer, _ = _assess(sample_cases.CLEAN_DECLARATION)
    assert [name for name, _ in tracer.spans] == ["conflicts_register.assess"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose screening is slow, in which market, on which kind", no more."""
    tracer, _ = _assess(sample_cases.CLEAN_DECLARATION)
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "assess"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["tenant"] == sample_cases.TENANT
    assert attributes["market"] == sample_cases.CLEAN_DECLARATION.market
    assert attributes["kind"] == sample_cases.CLEAN_DECLARATION.kind.value


@pytest.mark.parametrize(
    "declaration",
    [
        sample_cases.CLEAN_DECLARATION,
        sample_cases.FLAGGED_DECLARATION,
        sample_cases.RESTRICTED_PAD,
    ],
    ids=["clean", "flagged", "restricted-pad"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_verdict(
    declaration: Declaration,
) -> None:
    """A flagged declaration must not start attaching its findings, or names, to the span."""
    tracer, _ = _assess(declaration)
    for _, attributes in tracer.spans:
        assert set(attributes) == _ASSESS_KEYS


def test_no_span_attribute_carries_declaration_content_or_the_planted_identifier() -> None:
    """The declaration used here has an NRIC planted in its description, so a leak would show."""
    tracer, result = _assess(sample_cases.FLAGGED_DECLARATION)
    emitted = _emitted(tracer)

    forbidden = [
        sample_cases.PLANTED_NRIC,
        sample_cases.FLAGGED_DECLARATION.description,
        "Vega Supplies",
        "vega.ops@vega.example",
        sample_cases.FLAGGED_DECLARATION.employee,
        sample_cases.FLAGGED_DECLARATION.id,
        result.subject,
        result.summary,
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal not in emitted, f"a span attribute carried {literal!r}"
        assert literal.lower() not in emitted.lower(), f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _ = _assess(sample_cases.FLAGGED_DECLARATION)
    values: list[Any] = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
