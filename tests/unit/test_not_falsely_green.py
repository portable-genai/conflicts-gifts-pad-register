"""Every metric is proven able to go RED on a deliberate mutant (the not-falsely-green rule).

A metric that cannot fail proves nothing. Each proof below feeds a CLEAN input that must pass and
a DEGRADED input that must fail, and asserts the metric separates them:

* ``pii_safety``          : the SHIPPED ``run_eval.pii_safety`` over the SHIPPED
  ``run_eval.audit_texts``, falsified with an audit row whose summary is clean and whose citation
  leaks. The previous version of this proof scored a local one-line helper defined three lines
  above the assertion. It passed, and it proved nothing about the gate: the shipped metric read
  ``redacted_summary`` and nothing else, which is the ONE field the redactor was already masking,
  so it asked the redactor whether it had redacted and believed the answer. It reported
  ``pii_safety 1.000 PASS`` for a run whose audit record carried
  ``"source_id": "declaration:g-gift-over-S1234567D"``.
* ``screening_precision`` : the real engine (clean) vs the wildcard-rule mutant, which flags an
  adversarial near-miss symbol and drops precision below 1.0. This is the exact defect the
  restricted-list detector's exact-match on the instrument identity exists to prevent.
* ``extraction_accuracy`` : a correct entity resolver (clean) vs one that returns a wrong but
  schema-valid counterparty, which ingestion would use.
* ``groundedness``        : a narration that restates the engine's figures (clean) vs one that
  invents a figure the engine never produced.
"""

from __future__ import annotations

import json
from typing import Any

import run_eval as ev
from agent_eval_kit import assert_can_go_red, assert_each_can_go_red

from conflicts_gifts_pad_register.adapters.local.audit import LocalAuditAdapter
from conflicts_gifts_pad_register.adapters.local.llm import LocalLlmAdapter
from conflicts_gifts_pad_register.adapters.local.reference_store import LocalReferenceStore
from conflicts_gifts_pad_register.assembly import build_assessment_service
from conflicts_gifts_pad_register.config import Settings, build_container
from conflicts_gifts_pad_register.domain.assessment_service import is_grounded
from conflicts_gifts_pad_register.domain.ingestion_service import IngestionService
from conflicts_gifts_pad_register.domain.kernel import Severity
from conflicts_gifts_pad_register.domain.models import (
    ScreeningFinding,
    ScreeningOutcome,
    ScreeningResult,
)
from conflicts_gifts_pad_register.domain.screening_engine import ScreeningEngine
from conflicts_gifts_pad_register.screening_pack import pack_for

from tests.fixtures import sample_cases

_SETTINGS = Settings(profile="local")


# --------------------------------------------------------------------------- #
# pii_safety
# --------------------------------------------------------------------------- #
_PLANTED = (sample_cases.PLANTED_NRIC,)

#: The summary is CLEAN in both rows. That is the whole point: the summary was never the field
#: that leaked, so a metric that only reads it scores these two identically.
_CLEAN_ROW: dict[str, Any] = {
    "action": "assess",
    "actor": sample_cases.ACTOR,
    "redacted_summary": "gift declaration flagged :: NRIC [REDACTED:SG_NRIC_FIN] on the slip",
    "citations": [
        {
            "source_id": "declaration:dec-flagged",
            "title": "Declaration under screening",
            "snippet": "as_of 2026-08-08; 1 rule(s) fired",
        }
    ],
}

#: Redaction off, in the citation only (the mutant the shipped metric used to score 1.000). The
#: locator is the field that carries it: the declaration id is an unvalidated client string.
_LEAKY_ROW: dict[str, Any] = {
    **_CLEAN_ROW,
    "citations": [
        {
            "source_id": f"declaration:dec-{sample_cases.PLANTED_NRIC}",
            "title": "Declaration under screening",
            "snippet": f"as_of 2026-08-08; NRIC {sample_cases.PLANTED_NRIC} on the slip",
        }
    ],
}


def _score(rows: list[dict[str, Any]]) -> float:
    """The gate's own scorer over the gate's own field selection. No re-implementation here."""
    return ev.pii_safety(ev.audit_texts(rows), _PLANTED)


def test_pii_safety_can_go_red() -> None:
    assert_can_go_red(
        _score,
        green=[_CLEAN_ROW],
        red=[_LEAKY_ROW],
        threshold=ev.THRESHOLDS["pii_safety"],
        metric="pii_safety",
    )


def test_pii_safety_is_green_on_the_record_the_real_service_writes() -> None:
    """Green, and green over a real run rather than over an empty list of nothing."""
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    build_assessment_service(container).assess(
        sample_cases.PII_LOCATOR_DECLARATION, actor=sample_cases.ACTOR
    )
    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)

    texts = ev.audit_texts(audit.log.read_all())
    assert any("[REDACTED:" in text for text in texts), (
        "the scan found no redaction marker, so it is reading fields that carry no content "
        "and its green means nothing"
    )
    assert ev.pii_safety(texts, (*_PLANTED, sample_cases.PLANTED_EMAIL)) == 1.0


def test_the_scan_excludes_the_actor_so_it_can_ever_be_green() -> None:
    """The caveat, pinned: widening this to whole rows makes the metric permanently red.

    ``actor`` is the verified principal and is an address by design. A well-meaning "scan the
    whole record" change would make every run fail on the attribution column, and the next
    person would relax the threshold rather than narrow the scan.
    """
    row: dict[str, Any] = {**_CLEAN_ROW, "actor": "analyst@bank.example"}
    assert ev.pii_safety(ev.audit_texts([row]), _PLANTED) == 1.0


# --------------------------------------------------------------------------- #
# screening_precision (per rule family, via assert_each_can_go_red)
# --------------------------------------------------------------------------- #
_SNAPSHOT = LocalReferenceStore(_SETTINGS).snapshot(sample_cases.AS_OF)
_PACK = pack_for()
_INGESTION = IngestionService(LocalLlmAdapter(_SETTINGS))

#: One symbol that IS restricted and one adversarial near-miss that is NOT. Exact match keeps the
#: near-miss out; the wildcard mutant lets it in.
_LABELLED = ((sample_cases.RESTRICTED_PAD, True), (sample_cases.NEAR_MISS_PAD, False))


def _restricted_precision(engine: ScreeningEngine) -> float:
    true_positive = false_positive = 0
    for declaration, should_flag in _LABELLED:
        result = engine.screen(_INGESTION.normalize(declaration), _SNAPSHOT, _PACK)
        fired = any(f.rule_id == "restricted_list" for f in result.findings)
        if fired and should_flag:
            true_positive += 1
        elif fired and not should_flag:
            false_positive += 1
    total = true_positive + false_positive
    return true_positive / total if total else 1.0


def test_screening_precision_can_go_red_per_rule() -> None:
    assert_each_can_go_red(
        _restricted_precision,
        {"restricted_list": (ScreeningEngine(), ScreeningEngine(match_any=True))},
        threshold=1.0,
        metric="screening_precision",
    )


# --------------------------------------------------------------------------- #
# extraction_accuracy
# --------------------------------------------------------------------------- #
class _WrongEntityLlm:
    """A schema-valid model that resolves the WRONG counterparty (the degraded case)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, prompt: str, *, schema: dict[str, object] | None = None) -> str:
        return json.dumps({"counterparty": "Wrong Counterparty (FICTIONAL)"})


def _extraction_accuracy(llm: Any) -> float:
    resolved = IngestionService(llm).normalize(sample_cases.FLAGGED_DECLARATION)
    return 1.0 if resolved.counterparty_entity == "Vega Supplies (FICTIONAL)" else 0.0


def test_extraction_accuracy_can_go_red() -> None:
    assert_can_go_red(
        _extraction_accuracy,
        green=LocalLlmAdapter(_SETTINGS),  # resolves the entity in the text
        red=_WrongEntityLlm(_SETTINGS),  # a valid but wrong answer ingestion would use
        threshold=0.80,
        metric="extraction_accuracy",
    )


# --------------------------------------------------------------------------- #
# groundedness
# --------------------------------------------------------------------------- #
_RESULT = ScreeningResult(
    declaration_id="dec",
    outcome=ScreeningOutcome.FLAGGED,
    as_of="2026-08-08",
    findings=(
        ScreeningFinding(
            rule_id="gift_threshold",
            reason="gift of 25000 SGD (minor units) exceeds the 10000 threshold",
            severity=Severity.HIGH,
        ),
    ),
)


def _groundedness(text: str) -> float:
    return 1.0 if is_grounded(text, _RESULT) else 0.0


def test_groundedness_can_go_red() -> None:
    assert_can_go_red(
        _groundedness,
        green="gift of 25000 exceeds 10000 as of 2026-08-08",  # every figure is the engine's
        red="gift of 99999 warrants escalation",  # 99999 is invented; the engine never said it
        threshold=1.0,
        metric="groundedness",
    )
