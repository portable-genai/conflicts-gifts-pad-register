"""The deterministic screening engine: pure decision, replayable, one detector per rule.

The consequential decision (which rules fired, the CLEAR / FLAGGED outcome, the severity) is
pure stdlib and replayable from an ``as_of`` reference snapshot; an LLM would only narrate it,
never produce it. The engine mirrors the REQUIRE / EXCLUDE rule shape of a suitability engine:
each detector is a named rule, and the result records EXACTLY which rules fired and why.

Four detectors, each a rule with a stable id:

* ``restricted_list``  a personal-account deal on a symbol that is on the restricted list as of
  the declaration's effective date. Exact match on the instrument identity, never the free-text
  name, so an adversarial near-miss name cannot match a restricted symbol.
* ``blackout_window``  a personal-account deal on a symbol inside a dealing blackout as of that
  date (for example a results close period).
* ``mnpi_conflict``    a personal-account deal on a symbol the employee holds material
  non-public information on as of that date. The most severe: dealing on MNPI is market abuse.
* ``gift_threshold``   a gift or entertainment declaration above the per-role, per-market
  threshold in the pack. An UNCONFIGURED threshold is a gap that flags for review, never a pass.

Thresholds are pack data loaded outside ``domain/`` (``screening_pack.py``), so the engine holds
no policy constant. Determinism: same inputs, same output. No clock, no randomness, no network.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..screening_pack import ScreeningPack
from .kernel import Citation, Severity
from .models import (
    DeclarationKind,
    NormalizedDeclaration,
    ScreeningFinding,
    ScreeningOutcome,
    ScreeningResult,
)
from .reference_models import ReferenceSnapshot

_RESTRICTED = "restricted_list"
_BLACKOUT = "blackout_window"
_MNPI = "mnpi_conflict"
_GIFT = "gift_threshold"
_UNCONFIGURED = "gift_threshold_unconfigured"

#: Severity ordered most severe first, so the assessment can report the worst finding.
_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
)


@dataclass(frozen=True, slots=True)
class ScreeningEngine:
    """Pure, deterministic screening of one normalised declaration against a reference snapshot.

    ``match_any`` is a deliberate seam for the not-falsely-green proof ONLY: with it True the
    restricted-list detector matches every symbol (the wildcard mutant), which turns an
    adversarial near-miss into a false positive and drives screening precision below 1.0. It is
    never True in production; the engine is constructed with the default.
    """

    match_any: bool = False

    def screen(
        self,
        declaration: NormalizedDeclaration,
        snapshot: ReferenceSnapshot,
        pack: ScreeningPack,
    ) -> ScreeningResult:
        decl = declaration.declaration
        findings: list[ScreeningFinding] = []

        instrument = declaration.instrument
        if instrument is not None:
            findings.extend(self._instrument_findings(declaration, snapshot))

        if decl.kind in (DeclarationKind.GIFT, DeclarationKind.ENTERTAINMENT):
            finding = self._gift_finding(declaration, pack)
            if finding is not None:
                findings.append(finding)

        outcome = ScreeningOutcome.FLAGGED if findings else ScreeningOutcome.CLEAR
        citations = tuple(f.citation for f in findings if f.citation is not None)
        return ScreeningResult(
            declaration_id=decl.id,
            outcome=outcome,
            as_of=snapshot.as_of,
            findings=tuple(findings),
            citations=citations,
        )

    # ------------------------------------------------------------------ #
    # Detectors
    # ------------------------------------------------------------------ #
    def _instrument_findings(
        self, declaration: NormalizedDeclaration, snapshot: ReferenceSnapshot
    ) -> list[ScreeningFinding]:
        instrument = declaration.instrument
        assert instrument is not None
        symbol = instrument.identity
        employee = declaration.declaration.employee
        out: list[ScreeningFinding] = []

        restricted = self._restricted_hit(symbol, snapshot)
        if restricted is not None:
            out.append(
                ScreeningFinding(
                    rule_id=_RESTRICTED,
                    reason=(
                        f"symbol {symbol} is on the restricted list as of {snapshot.as_of}: "
                        f"{restricted.reason}"
                    ),
                    severity=Severity.HIGH,
                    citation=restricted.citation,
                )
            )

        blackout = snapshot.in_blackout(symbol)
        if blackout is not None:
            out.append(
                ScreeningFinding(
                    rule_id=_BLACKOUT,
                    reason=(
                        f"symbol {symbol} is inside a dealing blackout as of {snapshot.as_of}: "
                        f"{blackout.reason}"
                    ),
                    severity=Severity.HIGH,
                    citation=blackout.citation,
                )
            )

        mnpi = snapshot.mnpi_for(symbol, employee)
        if mnpi is not None:
            out.append(
                ScreeningFinding(
                    rule_id=_MNPI,
                    reason=(
                        f"employee holds material non-public information on {symbol} as of "
                        f"{snapshot.as_of}: {mnpi.reason}"
                    ),
                    severity=Severity.CRITICAL,
                    citation=mnpi.citation,
                )
            )
        return out

    def _restricted_hit(self, symbol: str, snapshot: ReferenceSnapshot):  # type: ignore[no-untyped-def]
        if self.match_any:
            # The wildcard mutant: match the first restricted entry regardless of symbol. Only
            # ``assert_can_go_red`` ever constructs the engine this way.
            return snapshot.restricted[0] if snapshot.restricted else None
        return snapshot.is_restricted(symbol)

    @staticmethod
    def _gift_finding(
        declaration: NormalizedDeclaration, pack: ScreeningPack
    ) -> ScreeningFinding | None:
        decl = declaration.declaration
        limit = pack.gift_limit(decl.employee_role, decl.market, decl.kind)
        if limit is None:
            # Fail closed: an unconfigured threshold is a gap, not a clean pass.
            return ScreeningFinding(
                rule_id=_UNCONFIGURED,
                reason=(
                    f"no {decl.kind.value} threshold configured for role {decl.employee_role!r} "
                    f"in market {decl.market!r}; screening cannot clear an unconfigured limit"
                ),
                severity=Severity.MEDIUM,
                citation=None,
            )
        if declaration.amount_minor > limit.threshold_minor:
            reason = (
                f"{decl.kind.value} of {declaration.amount_minor} {limit.currency} (minor units) "
                f"exceeds the {limit.threshold_minor} threshold for role {decl.employee_role!r} "
                f"in market {decl.market!r}"
            )
            return ScreeningFinding(
                rule_id=_GIFT,
                reason=reason,
                severity=limit.severity,
                citation=limit.citation,
            )
        return None

    # ------------------------------------------------------------------ #
    # Helpers used by the assessment service
    # ------------------------------------------------------------------ #
    @staticmethod
    def worst_severity(result: ScreeningResult) -> Severity:
        """The most severe finding on a result, or LOW when it cleared."""
        present = {f.severity for f in result.findings}
        for severity in _SEVERITY_ORDER:
            if severity in present:
                return severity
        return Severity.LOW

    @staticmethod
    def subject_citation(result: ScreeningResult) -> Citation:
        """A provenance anchor tying the assessment back to the declaration it screened."""
        return Citation(
            source_id=f"declaration:{result.declaration_id}",
            title="Declaration under screening",
            snippet=f"as_of {result.as_of}; {len(result.findings)} rule(s) fired",
        )
