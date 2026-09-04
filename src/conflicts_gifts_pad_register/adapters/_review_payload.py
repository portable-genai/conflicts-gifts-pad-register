"""Shared conversion from an escalated result to an ``review-kit`` Review payload.

Lives in the adapter layer, not the pure domain, because it depends on the kit. The subject, summary
and every citation snippet are redacted BEFORE they leave the process (the same
redact-before-anything rule the audit write obeys), using the shared ``pii-kit``, so no raw
identifier reaches human-review-console over the wire; human-review-console redacts again before its
own audit write (defence in depth). ``maker`` and ``tenant`` are asserted here and trusted by
human-review-console because the caller is an authenticated S2S service; per-hop on-behalf-of token
exchange is the deferred next layer.
"""

from __future__ import annotations

import re

from pii_kit import NATIONAL_ID_PATTERNS, UNIVERSAL_PATTERNS, national_patterns_for
from pii_kit import redact as pii_redact
from review_kit import Citation as KitCitation
from review_kit import Review

from ..domain.kernel import Severity
from ..domain.models import ConflictAssessment

#: Cap the citations carried on the wire: enough for a reviewer to trace the decision without
#: copying the whole evidence set into the console.
_MAX_CITATIONS = 8

#: The console is a SHARED sink: a case filed in one market may still quote another market's
#: national id, so the payload is scrubbed against every jurisdiction's rows plus the universal
#: email/phone rows, whatever this deployment's own ``domain.pii.JURISDICTIONS`` selects.
_ALL_PATTERNS = (
    *national_patterns_for(tuple(NATIONAL_ID_PATTERNS.keys())),
    *UNIVERSAL_PATTERNS,
)

#: Bands that demand dual control (two approvals) rather than a single checker.
_DUAL_CONTROL = (Severity.CRITICAL,)


def _redact(text: str) -> str:
    """Mask every jurisdiction's identifiers plus email/phone, and normalise whitespace."""
    return re.sub(r"\s+", " ", pii_redact(text, _ALL_PATTERNS)).strip()


def _kit_citations(result: ConflictAssessment) -> tuple[KitCitation, ...]:
    """Every field of every citation is masked, not only the snippet.

    A locator is routinely built from client text (``declaration:<the client's own register
    id>``), so masking only the snippet let the identifier cross to the shared console in the
    field named like a key. De-duplication keys off the REDACTED locator, so two declarations
    that differ only in a masked identifier collapse to one citation rather than both crossing
    the wire.
    """
    seen: set[str] = set()
    out: list[KitCitation] = []
    for citation in result.citations:
        source_id = _redact(citation.source_id)
        if source_id in seen:
            continue
        seen.add(source_id)
        out.append(
            KitCitation(
                source_id=source_id,
                title=_redact(citation.title),
                snippet=_redact(citation.snippet),
            )
        )
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


def result_to_review(result: ConflictAssessment, *, maker: str, tenant: str = "") -> Review:
    """Build the review a producer submits to human-review-console when an assessment escalates.

    The declaration id is redacted ONCE and reused for the case reference and the idempotency
    key. It looks like an opaque handle and is not one: it is ``AssessRequest.id``, an
    unvalidated string the client puts in the request body, and it is the SAME string whose use
    as a citation locator (``declaration:<id>``) was the C3 leak in this repo. Masking it in the
    locator and leaving it raw in the two fields beside it would have moved the leak rather than
    closed it, which is exactly what happened until this change: the citation read
    ``declaration:dec-[REDACTED:SG_NRIC_FIN]`` while ``case_ref`` read ``dec-S1234567D``.

    The cost is named rather than hidden: two declarations whose ids differ ONLY in a masked
    identifier now share a source key and collapse to one review at the console. That is the
    right trade against publishing the identifier on a shared surface, and an id distinguished
    solely by a national id is not an id anyone should be keying on. The key stays stable across
    retries because ``pii_kit.redact`` substitutes a fixed literal token per pattern, with no
    hash and no salt, so the same id always yields the same masked key;
    ``test_the_review_source_key_is_stable_so_a_retry_stays_idempotent`` pins that, because the
    trade is only defensible while it holds.
    """
    case_ref = _redact(result.declaration_id)
    return Review(
        action="conflicts_gifts_pad_register:assess",
        subject=_redact(result.subject),
        maker=maker,
        tenant=tenant,
        summary=_redact(result.summary),
        severity=result.severity.value,
        required_approvals=2 if result.severity in _DUAL_CONTROL else 1,
        sod_group="conflicts_gifts_pad_register-maker-checker",
        case_ref=case_ref,
        # Producer-owned, tenant-scoped key so a retried delivery is idempotent at the console.
        source_key=f"conflicts-gifts-pad-register:{case_ref}:{result.severity.value}",
        citations=_kit_citations(result),
    )
