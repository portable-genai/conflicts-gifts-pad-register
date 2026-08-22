#!/usr/bin/env python3
"""Evaluation gate for Conflicts, Gifts and PAD Register (Rgc11).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``AssessmentService`` against a golden set with SDK-free local adapters and scores four metrics,
  each against the DATASET'S OWN labelled oracle, never against the pipeline's own verdict.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp`` profile),
  via ``agent_eval_kit.PromotionGateClient``.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from conflicts_gifts_pad_register.assembly import build_assessment_service
from conflicts_gifts_pad_register.config import Settings, build_container
from conflicts_gifts_pad_register.domain.assessment_service import is_grounded
from conflicts_gifts_pad_register.domain.ingestion_service import IngestionService
from conflicts_gifts_pad_register.domain.models import Declaration, DeclarationKind, Instrument
from conflicts_gifts_pad_register.domain.pii import PII_PATTERNS

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {
    "decision_accuracy": 1.00,
    "extraction_accuracy": 0.80,
    "groundedness": 1.00,
    "pii_safety": 0.99,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "conflicts-gifts-pad-register"


def _load(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def audit_texts(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of every audit row, which is what a leak scan has to read.

    Collecting ``redacted_summary`` and nothing else would name the one field the
    redactor already masks: the metric would ask the redactor whether it had redacted, believe
    the answer, and reported a green while the SAME record's citation carried the identifier
    verbatim. Citations travel inside the record, and they carry raw client text in ``snippet``
    and, routinely, in ``source_id`` (``declaration:<the client's own register id>``, which is an
    unvalidated string on the API request).

    ``actor`` is excluded deliberately: it is the verified principal and an address by design, so
    a blanket scan over a whole row could never go green, and a metric nobody can make green
    gets deleted rather than fixed.
    """
    texts: list[str] = []
    for row in rows:
        texts.append(str(row.get("redacted_summary", "")))
        texts.append(json.dumps(row.get("citations", []), sort_keys=True))
    return texts


def pii_safety(records: Sequence[str], planted: Sequence[str]) -> float:
    """No identifier may survive into an audit record, by the pack rows OR by planted literal.

    Two oracles, because they fail independently: the pack scan uses the same rows the redactor
    masks with (so a redactor that skipped a field is caught), and the planted-literal check
    fires even if a pattern row is broken (so a pack that stopped matching is caught too).
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def _declaration(case: dict[str, object]) -> Declaration:
    symbol = str(case.get("symbol") or "")
    return Declaration(
        id=str(case["id"]),
        tenant="demo-bank",
        employee=str(case["employee"]),
        employee_role=str(case["employee_role"]),
        market=str(case["market"]),
        kind=DeclarationKind(str(case["kind"])),
        description=str(case["description"]),
        as_of=str(case["as_of"]),
        counterparty=str(case.get("counterparty") or ""),
        amount_minor=int(case.get("amount_minor") or 0),
        currency=str(case.get("currency") or ""),
        instrument=Instrument(symbol=symbol) if symbol else None,
    )


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    service = build_assessment_service(container)
    ingestion = IngestionService(container.llm)

    decision: list[float] = []
    extraction: list[float] = []
    grounded: list[float] = []
    for case in cases:
        declaration = _declaration(case)
        result = service.assess(declaration, actor="eval-bot")
        # decision_accuracy: outcome vs the dataset's own expected_outcome (independent oracle).
        decision.append(1.0 if result.screening.outcome.value == case["expected_outcome"] else 0.0)
        # extraction_accuracy: model-resolved counterparty vs the labelled expected_counterparty.
        resolved = ingestion.normalize(declaration).counterparty_entity
        extraction.append(1.0 if resolved == str(case.get("expected_counterparty") or "") else 0.0)
        # groundedness: the narration invents no figure the engine did not put on the table.
        grounded.append(1.0 if is_grounded(result.summary, result.screening) else 0.0)

    # pii_safety: no raw identifier may survive into any audit record. `audit_texts` decides
    # WHICH fields count as the record's content; see its docstring for why the summary alone is
    # not the record.
    records = audit_texts(container.audit.log.read_all())
    planted = [str(case["planted"]) for case in cases if case.get("planted")]

    results = (
        EvalMetricResult.scored(
            "decision_accuracy", _mean(decision), THRESHOLDS["decision_accuracy"]
        ),
        EvalMetricResult.scored(
            "extraction_accuracy", _mean(extraction), THRESHOLDS["extraction_accuracy"]
        ),
        EvalMetricResult.scored("groundedness", _mean(grounded), THRESHOLDS["groundedness"]),
        EvalMetricResult.scored(
            "pii_safety", pii_safety(records, planted), THRESHOLDS["pii_safety"]
        ),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"CONFLICTSPAD_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("CONFLICTSPAD_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-2.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for Rgc11.",
        )
    )
