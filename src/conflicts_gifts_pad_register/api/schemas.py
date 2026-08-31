"""API request/response schemas (Pydantic) mapped to/from the pure-domain models.

The request carries NO tenant and NO actor: identity is resolved server-side from the verified
principal, and the tenant comes from it, never from the body. A client that puts a tenant in the
body is ignored, which is the whole point of server-side identity.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.models import ConflictAssessment, Declaration, DeclarationKind, Instrument
from ..domain.reference_models import ReferenceSnapshot


class InstrumentModel(BaseModel):
    symbol: str
    name: str = ""
    isin: str = ""

    def to_domain(self) -> Instrument:
        return Instrument(symbol=self.symbol, name=self.name, isin=self.isin)


class AssessRequest(BaseModel):
    """One declaration to screen. The tenant is the verified principal's, never this body's."""

    id: str
    employee: str
    employee_role: str
    market: str
    kind: str
    description: str
    as_of: str
    counterparty: str = ""
    amount_minor: int = 0
    currency: str = ""
    instrument: InstrumentModel | None = None

    def to_domain(self, *, tenant: str) -> Declaration:
        return Declaration(
            id=self.id,
            tenant=tenant,
            employee=self.employee,
            employee_role=self.employee_role,
            market=self.market,
            kind=DeclarationKind(self.kind),
            description=self.description,
            as_of=self.as_of,
            counterparty=self.counterparty,
            amount_minor=self.amount_minor,
            currency=self.currency,
            instrument=self.instrument.to_domain() if self.instrument else None,
        )


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class FindingModel(BaseModel):
    rule_id: str
    reason: str
    severity: str


class AssessResponse(BaseModel):
    declaration_id: str
    subject: str
    market: str
    kind: str
    verdict: str
    severity: str
    decision: str
    summary: str
    requires_human_review: bool
    #: Where the escalation WENT (rule R8): the Hrz7 review id, or the local queue reference.
    #: Empty only when the assessment did not escalate.
    review_ref: str = ""
    findings: list[FindingModel] = []
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, result: ConflictAssessment, *, review_ref: str = "") -> AssessResponse:
        return cls(
            declaration_id=result.declaration_id,
            subject=result.subject,
            market=result.market,
            kind=result.kind.value,
            verdict=result.verdict.value,
            severity=result.severity.value,
            decision=result.decision.value,
            summary=result.summary,
            requires_human_review=result.requires_human_review,
            review_ref=review_ref,
            findings=[
                FindingModel(rule_id=f.rule_id, reason=f.reason, severity=f.severity.value)
                for f in result.screening.findings
            ],
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
        )


class ReferenceEntryModel(BaseModel):
    symbol: str
    reason: str
    effective_from: str = ""
    effective_to: str = ""
    insider: str = ""


class ReferenceSnapshotResponse(BaseModel):
    """The as-of restricted / blackout / MNPI snapshot Cmp1 reads over A2A."""

    as_of: str
    restricted: list[ReferenceEntryModel] = []
    blackouts: list[ReferenceEntryModel] = []
    mnpi: list[ReferenceEntryModel] = []

    @classmethod
    def from_domain(cls, snapshot: ReferenceSnapshot) -> ReferenceSnapshotResponse:
        return cls(
            as_of=snapshot.as_of,
            restricted=[
                ReferenceEntryModel(
                    symbol=r.identity,
                    reason=r.reason,
                    effective_from=r.window.effective_from,
                    effective_to=r.window.effective_to,
                )
                for r in snapshot.restricted
            ],
            blackouts=[
                ReferenceEntryModel(
                    symbol=b.identity,
                    reason=b.reason,
                    effective_from=b.window.effective_from,
                    effective_to=b.window.effective_to,
                )
                for b in snapshot.blackouts
            ],
            mnpi=[
                ReferenceEntryModel(
                    symbol=m.identity,
                    reason=m.reason,
                    effective_from=m.window.effective_from,
                    effective_to=m.window.effective_to,
                    insider=m.insider,
                )
                for m in snapshot.mnpi
            ],
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: Provenance the UI banner states on every page: where the runtime sits and which model
    #: answers. Both are read off the service because the browser cannot know either.
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "deterministic-offline-stub"
