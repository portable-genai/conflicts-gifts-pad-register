"""Vertical artifact models: the conflicts / gifts / personal-account-dealing register.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py``. The service's own name is deliberately not substituted into this docstring: a
rendered line whose length depends on ``friendly_name`` fails the repo's own format check for
no reason but the length of its name.

Everything consequential (which rules fired, the CLEAR / FLAGGED outcome, the approve / escalate
verdict, the severity) is decided by the deterministic engine in ``screening_engine.py``. The
model only narrates the already-fixed verdict, and it never appears in this module. A fork
building a different vertical rewrites this module and keeps ``kernel.py`` untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class DeclarationKind(LenientStrEnum):
    """The kinds of declaration the register screens. A member IS its wire value."""

    GIFT = "gift"
    ENTERTAINMENT = "entertainment"
    OUTSIDE_INTEREST = "outside_interest"
    POLITICAL_DONATION = "political_donation"
    PERSONAL_ACCOUNT_DEAL = "personal_account_deal"


class ScreeningOutcome(LenientStrEnum):
    CLEAR = "clear"  # no rule fired
    FLAGGED = "flagged"  # at least one rule fired: never auto-approved


class AssessmentVerdict(LenientStrEnum):
    APPROVE = "approve"  # CLEAR, still recorded and reviewable
    ESCALATE = "escalate"  # FLAGGED: routed to a human, never auto-executed


@dataclass(frozen=True, slots=True)
class Instrument:
    """A financial instrument a personal-account deal names.

    ``identity`` is the deterministic key screening compares on: the symbol upper-cased and
    stripped, never the free-text name. Restricted-list matching is exact on this key so an
    adversarial near-miss name cannot match a restricted symbol.
    """

    symbol: str
    name: str = ""
    isin: str = ""

    @property
    def identity(self) -> str:
        return self.symbol.strip().upper()


@dataclass(frozen=True, slots=True)
class Declaration:
    """One declaration as ingested: structured fields plus a free-text description.

    ``amount_minor`` is an integer in the currency's minor units (cents), so no float ever
    reaches the threshold comparison. ``as_of`` is the effective date (``YYYY-MM-DD``) the
    reference snapshot is replayed at, which is what makes screening reproducible.
    """

    id: str
    tenant: str
    employee: str
    employee_role: str
    market: str
    kind: DeclarationKind
    description: str
    as_of: str
    counterparty: str = ""
    amount_minor: int = 0
    currency: str = ""
    instrument: Instrument | None = None


@dataclass(frozen=True, slots=True)
class NormalizedDeclaration:
    """A declaration after deterministic normalisation and model-assisted entity resolution.

    The amount, the effective date and the instrument identity are owned by deterministic code
    (``ingestion_service.py``); only ``counterparty_entity`` is model-resolved from free text,
    under schema validation with a deterministic fallback, and it is enrichment, never an input
    to a consequential decision.
    """

    declaration: Declaration
    counterparty_entity: str
    amount_minor: int
    instrument: Instrument | None
    model_resolved: bool


@dataclass(frozen=True, slots=True)
class ScreeningFinding:
    """One rule that FIRED, why, and how severe. Only fired rules are carried on a result."""

    rule_id: str
    reason: str
    severity: Severity
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    """The deterministic screening verdict: which rules fired, replayable at ``as_of``."""

    declaration_id: str
    outcome: ScreeningOutcome
    as_of: str
    findings: tuple[ScreeningFinding, ...] = ()
    citations: tuple[Citation, ...] = ()

    @property
    def requires_human_review(self) -> bool:
        """A flagged declaration always needs a human: the register never auto-approves one."""
        return self.outcome is ScreeningOutcome.FLAGGED


@dataclass(frozen=True, slots=True)
class ConflictAssessment:
    """The consequential, escalatable artifact the register produces for one declaration.

    Carries the fields the human-review-console review payload reads (``subject``, ``summary``,
    ``severity``,
    ``citations``) so an escalation routes without a second mapping. ``verdict``, ``severity``
    and ``requires_human_review`` come from the deterministic engine; ``summary`` is the model's
    cited narration of that already-fixed verdict and may only restate engine findings.
    """

    declaration_id: str
    subject: str
    employee: str
    tenant: str
    market: str
    kind: DeclarationKind
    verdict: AssessmentVerdict
    severity: Severity
    decision: Decision
    summary: str
    screening: ScreeningResult
    requires_human_review: bool
    citations: tuple[Citation, ...] = field(default_factory=tuple)
