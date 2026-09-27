"""AssessmentService: the register orchestrator. Engines decide; the model narrates.

The pipeline for one declaration:

    normalize (deterministic amount/date/instrument; model-resolved counterparty)
      -> reference snapshot at the declaration's as_of (window-filtered, replayable)
      -> deterministic screening (which rules fired, CLEAR / FLAGGED, severity)
      -> verdict FIXED by the engine: FLAGGED -> ESCALATE, CLEAR -> APPROVE
      -> model drafts a cited rationale over the ALREADY-FIXED verdict (grounded, or discarded)
      -> redact PII, then write the audit event (R1 / P-04)
      -> ConflictAssessment (requires_human_review set; the register never auto-approves a flag)

The model has no say in the verdict, the severity or whether review is required. Its narration is
accepted only when it is GROUNDED in the engine's findings (no invented figure), and otherwise a
deterministic summary is used.

Rule R1: every generation call is screened INPUT before (the prompt as sent) and OUTPUT after
(the raw reply, before it is parsed or grounded), in ingestion and in narration alike. Both
calls are optional by design, each with a deterministic fallback, so a refused screen (a block,
or a guardrail that could not decide) discards that model step, uses the fallback, and is
audited on its own ``Decision.BLOCKED`` row before the assessment's row. The refused text is
never used and never recorded. Routing to human-review-console (rule R8) happens on the driving
surfaces (API, CLI, agent), in the same call that produced the result, exactly as the reference
build does.

Pure domain code: ports and the deterministic engine come in by constructor injection; no SDK.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.guardrail import GuardrailPort
from ..ports.llm import LlmPort
from ..ports.observability import ObservabilityTracerPort
from ..ports.reference_store import ReferenceStorePort
from ..screening_pack import ScreeningPack
from .guardrail_screen import screen_text
from .ingestion_service import IngestionService
from .kernel import AuditEvent, Decision, Direction, GuardrailRefusal, Severity, utcnow
from .models import (
    AssessmentVerdict,
    ConflictAssessment,
    Declaration,
    ScreeningResult,
)
from .pii import PII_PATTERNS
from .screening_engine import ScreeningEngine

_RATIONALE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"rationale": {"type": "string"}},
    "required": ["rationale"],
}

#: Any run of digits in the model's narration must be one the engine put on the table, else the
#: narration is discarded as ungrounded. This is what stops a fabricated amount reaching a page.
_NUMBER = re.compile(r"\d+")

#: One span per assessed declaration. Structural attributes only: see :meth:`.assess`.
_ASSESS_SPAN = "conflicts_register.assess"

#: The step name a refusal of the narration call is audited under.
NARRATE_STEP = "narration"


class AssessmentService:
    """Assess one declaration into a cited, human-reviewed conflict assessment."""

    def __init__(
        self,
        ingestion: IngestionService,
        reference_store: ReferenceStorePort,
        audit: AuditSinkPort,
        llm: LlmPort,
        guardrail: GuardrailPort,
        pack: ScreeningPack,
        tracer: ObservabilityTracerPort,
        engine: ScreeningEngine | None = None,
    ) -> None:
        self._ingestion = ingestion
        self._reference = reference_store
        self._audit = audit
        self._llm = llm
        self._guardrail = guardrail
        self._pack = pack
        self._tracer = tracer
        self._engine = engine or ScreeningEngine()

    def assess(self, declaration: Declaration, *, actor: str) -> ConflictAssessment:
        """Screen one declaration end to end and return the cited, review-gated assessment.

        The whole path runs inside one span. Its attributes are STRUCTURAL only, never the
        employee, the counterparty, the declaration id or the description text: a trace backend
        is not the WORM audit trail. It has no redaction stage, a wider read audience and no
        retention rule written against a regulator's requirement, so anything content-shaped
        that reaches a span has left the boundary the ``redact`` call exists to hold, silently.
        """
        with self._tracer.span(
            _ASSESS_SPAN,
            action="assess",
            actor=actor,
            tenant=declaration.tenant,
            market=declaration.market,
            kind=declaration.kind.value,
        ):
            normalized = self._ingestion.normalize(declaration)
            snapshot = self._reference.snapshot(declaration.as_of)
            result = self._engine.screen(normalized, snapshot, self._pack)

            flagged = result.requires_human_review
            verdict = AssessmentVerdict.ESCALATE if flagged else AssessmentVerdict.APPROVE
            severity = ScreeningEngine.worst_severity(result)
            decision = Decision.ESCALATED if flagged else Decision.ALLOWED

            citations = (ScreeningEngine.subject_citation(result), *result.citations)
            summary, narration_refusals = self._narrate(declaration, result, verdict, severity)

            subject = (
                f"{declaration.employee} / "
                f"{normalized.counterparty_entity or declaration.kind.value}"
            )

            # Every refused generation call is audited BLOCKED first, on its own row: the
            # assessment below completed on deterministic text, and these say why it had to.
            for refusal in (*normalized.guardrail_refusals, *narration_refusals):
                self._audit_blocked(refusal, actor=actor, severity=severity)

            # Redact BEFORE the audit write: no employee name, counterparty or identifier from
            # the declaration text reaches the WORM record. The raw declaration text is included
            # so the record says what was screened, which is exactly why it has to be masked on
            # the way in.
            audited = f"{subject} :: {summary} :: {declaration.description}"
            self._audit.record(
                AuditEvent(
                    action="assess",
                    actor=actor,
                    decision=decision,
                    severity=severity,
                    redacted_summary=redact(audited, PII_PATTERNS),
                    citations=citations,
                    timestamp=utcnow(),
                )
            )

            return ConflictAssessment(
                declaration_id=declaration.id,
                subject=subject,
                employee=declaration.employee,
                tenant=declaration.tenant,
                market=declaration.market,
                kind=declaration.kind,
                verdict=verdict,
                severity=severity,
                decision=decision,
                summary=summary,
                screening=result,
                requires_human_review=flagged,
                citations=citations,
            )

    # ------------------------------------------------------------------ #
    # Narration (restates the engine's findings; never decides anything)
    # ------------------------------------------------------------------ #
    def _narrate(
        self,
        declaration: Declaration,
        result: ScreeningResult,
        verdict: AssessmentVerdict,
        severity: Severity,
    ) -> tuple[str, tuple[GuardrailRefusal, ...]]:
        """Return ``(summary, refusals)``: the grounded draft, or the deterministic summary.

        Rule R1: the prompt is screened INPUT before the call and the raw draft OUTPUT before it
        is parsed or grounded, and each screen's text is the text used from then on. A refused
        direction degrades to the deterministic summary exactly as an ungrounded or malformed
        draft already does (the engine fixed the verdict, so narration is all that is at stake),
        and the refusal is returned for the caller to audit.
        """
        deterministic = deterministic_summary(declaration, result, verdict, severity)
        prompt = screen_text(
            self._guardrail,
            self._prompt(declaration, result, verdict, deterministic),
            Direction.INPUT,
            step=NARRATE_STEP,
        )
        if isinstance(prompt, GuardrailRefusal):
            return deterministic, (prompt,)
        try:
            # Narration restates a verdict the engine already fixed: it samples freely (no
            # temperature sent), and an ungrounded draft is still discarded below.
            raw = self._llm.generate(prompt, schema=_RATIONALE_SCHEMA, temperature=None)
        except Exception:
            return deterministic, ()
        reply = screen_text(self._guardrail, raw, Direction.OUTPUT, step=NARRATE_STEP)
        if isinstance(reply, GuardrailRefusal):
            return deterministic, (reply,)
        drafted = self._parse(reply)
        if drafted is None or not is_grounded(drafted, result):
            # A malformed or ungrounded narration is discarded: the deterministic summary, built
            # from the engine's own findings, is always grounded.
            return deterministic, ()
        return drafted, ()

    def _audit_blocked(self, refusal: GuardrailRefusal, *, actor: str, severity: Severity) -> None:
        """Audit one refused generation call ``BLOCKED`` (rule R1/R2).

        Never carries the refused text, nor the declaration's subject or description (either may
        be the very thing refused): only which step was refused, in which direction, and why.
        """
        self._audit.record(
            AuditEvent(
                action="assess",
                actor=actor,
                decision=Decision.BLOCKED,
                severity=severity,
                redacted_summary=redact(
                    f"{refusal.step} blocked ({refusal.direction.value}): {refusal.reason}; "
                    "deterministic text used instead",
                    PII_PATTERNS,
                ),
                citations=(),
                timestamp=utcnow(),
            )
        )

    @staticmethod
    def _prompt(
        declaration: Declaration,
        result: ScreeningResult,
        verdict: AssessmentVerdict,
        deterministic: str,
    ) -> str:
        findings = "; ".join(f.reason for f in result.findings) or "no rule fired"
        return (
            "Draft a one or two sentence rationale for the conflicts register. The verdict is "
            f"already decided: {verdict.value}. Restate ONLY these engine findings and invent no "
            f"figure that is not in them.\n\nFINDINGS: {findings}\n\nBASELINE: {deterministic}\n\n"
            'Reply with JSON of the form {"rationale": "<text>"}.'
        )

    @staticmethod
    def _parse(raw: str) -> str | None:
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None
        rationale = obj.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            return None
        return rationale.strip()


def deterministic_summary(
    declaration: Declaration,
    result: ScreeningResult,
    verdict: AssessmentVerdict,
    severity: Severity,
) -> str:
    """A summary built from the engine's own output, so it is grounded by construction."""
    if not result.findings:
        return (
            f"{declaration.kind.value} declaration cleared screening as of {result.as_of}: no "
            f"rule fired. Verdict {verdict.value}, severity {severity.value}."
        )
    fired = ", ".join(f.rule_id for f in result.findings)
    return (
        f"{declaration.kind.value} declaration flagged as of {result.as_of}: {fired}. Verdict "
        f"{verdict.value}, severity {severity.value}; routed for human review."
    )


def is_grounded(text: str, result: ScreeningResult) -> bool:
    """True when every number in ``text`` appears in the engine's findings or the as_of date.

    The engine's findings and the as_of date are the only figures a narration may carry. A
    number in the narration that is in neither is a fabrication, and the narration is discarded.
    """
    allowed = " ".join(f.reason for f in result.findings) + " " + result.as_of
    allowed_numbers = set(_NUMBER.findall(allowed))
    return all(token in allowed_numbers for token in _NUMBER.findall(text))
