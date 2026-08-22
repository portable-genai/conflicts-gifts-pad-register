"""Nothing redaction removed survives anywhere else in the WORM record (check C3).

``AssessmentService.assess`` masked ``redacted_summary`` and then handed the SAME event its
citations untouched, so an identifier the summary no longer carried was persisted verbatim one
field away, in a record that is by design immutable and long-retained. The summary is not the
record.

The locator is the field that bites here. ``ScreeningEngine.subject_citation`` builds
``source_id=f"declaration:{result.declaration_id}"`` and the declaration id is an unvalidated
client string on the API request, so a citation's key-shaped field carries client text.

Two rules this suite holds, and they pull in opposite directions, which is why both are written
down:

* every CONTENT field is scanned: the summary, and each citation's locator, title and snippet.
* the ATTRIBUTION field is not. ``actor`` is the verified principal and is an address by design,
  so a blanket scan over a whole audit row could never go green, and a scan that "fixed" that by
  masking the actor would erase the only column that says who acted.

Scored two ways, as the eval metric is: the shared pack's own rows, plus the planted literals,
which still fire if a pattern row is broken.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from hex_service_kit import to_jsonable
from pii_kit import pack_leak
from review_kit import Review

from conflicts_gifts_pad_register.adapters._review_payload import result_to_review
from conflicts_gifts_pad_register.adapters.local.audit import LocalAuditAdapter
from conflicts_gifts_pad_register.config import Container
from conflicts_gifts_pad_register.domain.assessment_service import AssessmentService
from conflicts_gifts_pad_register.domain.models import Declaration
from conflicts_gifts_pad_register.domain.pii import PII_PATTERNS

from tests.fixtures import sample_cases

_PLANTED = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)


def _content(row: Mapping[str, Any]) -> str:
    """Every content-bearing field of one audit row, as one scannable blob.

    ``actor`` and the structural columns are excluded deliberately: see the module docstring.
    """
    return " ".join(
        (
            str(row.get("redacted_summary", "")),
            json.dumps(row.get("citations", []), sort_keys=True),
        )
    )


@pytest.mark.parametrize(
    "declaration",
    [sample_cases.FLAGGED_DECLARATION, sample_cases.PII_LOCATOR_DECLARATION],
    ids=["identifier-in-text", "identifier-in-locator-and-text"],
)
def test_no_identifier_reaches_the_audit_record(
    assessment_service: AssessmentService, container: Container, declaration: Declaration
) -> None:
    assessment_service.assess(declaration, actor=sample_cases.ACTOR)

    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    rows = list(audit.log.read_all())
    assert rows, "the assess path wrote no audit record, so this proves nothing"

    for row in rows:
        blob = _content(row)
        assert not pack_leak(blob, PII_PATTERNS), f"pack row matched in the WORM record: {blob}"
        for token in _PLANTED:
            assert token not in blob, f"planted {token!r} survived into the WORM record: {blob}"


def test_the_actor_is_kept_verbatim_because_it_is_attribution(
    assessment_service: AssessmentService, container: Container
) -> None:
    """The caveat, pinned: the principal is an address and must NOT be masked away."""
    assessment_service.assess(sample_cases.FLAGGED_DECLARATION, actor=sample_cases.ACTOR)

    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    actors = [str(row.get("actor", "")) for row in audit.log.read_all()]
    assert actors == [sample_cases.ACTOR]


#: The outbound review's ATTRIBUTION fields, excluded from the payload scan for the same reason
#: ``actor`` is excluded from the audit scan: the maker is the verified principal and is an
#: address by design, so a genuinely blanket scan could never go green. ``tenant`` is a partition
#: label the server derives from that principal, not client text.
_ATTRIBUTION_FIELDS = frozenset({"maker", "tenant"})


def _payload(review: Review) -> str:
    """The WHOLE serialised review, minus the named attribution fields.

    Serialised off the dataclass rather than from a hand-listed set of names, so a field added to
    ``Review`` later is scanned by DEFAULT instead of by somebody remembering to extend this.
    Listing only the three citation fields is exactly the set a reader thinks of as content, and
    ``case_ref`` and ``source_key`` carry the raw ``declaration_id`` straight past it: the id is
    ``AssessRequest.id``, an unvalidated client string, and it is the SAME string whose use as a
    citation locator is the leak this file is written to catch.
    """
    body = {
        name: value
        for name, value in to_jsonable(review).items()
        if name not in _ATTRIBUTION_FIELDS
    }
    return json.dumps(body, sort_keys=True, default=str)


def test_the_whole_review_payload_is_redacted_not_only_its_narrative_fields(
    assessment_service: AssessmentService,
) -> None:
    """The console is a shared sink, and every field of the payload lands on it.

    A citation LOCATOR crosses the wire like a snippet does, and so do ``case_ref`` and
    ``source_key``, whose structural names are the only reason anyone read them as keys rather
    than as the client string they are built from.
    """
    result = assessment_service.assess(
        sample_cases.PII_LOCATOR_DECLARATION, actor=sample_cases.ACTOR
    )
    review = result_to_review(result, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)

    blob = _payload(review)
    assert not pack_leak(blob, PII_PATTERNS), f"pack row matched in the review payload: {blob}"
    for token in _PLANTED:
        assert token not in blob, f"planted {token!r} crossed to the console: {blob}"


def test_the_review_source_key_is_stable_so_a_retry_stays_idempotent(
    assessment_service: AssessmentService,
) -> None:
    """The named cost of masking the case reference: the key must still survive a retry.

    ``pii_kit.redact`` substitutes a fixed literal token per pattern, with no hash and no salt,
    so the same declaration id always yields the same key. Pinned rather than assumed, because a
    masking style that ever became random would silently turn every retried delivery into a
    second review on the console.
    """
    result = assessment_service.assess(
        sample_cases.PII_LOCATOR_DECLARATION, actor=sample_cases.ACTOR
    )
    keys = {
        result_to_review(result, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT).source_key
        for _ in range(200)
    }

    assert len(keys) == 1, f"the idempotency key is not stable under redaction: {keys}"
    assert sample_cases.PLANTED_NRIC not in keys.pop()
