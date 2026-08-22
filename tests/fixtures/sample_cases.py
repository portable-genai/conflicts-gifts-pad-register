"""Canonical synthetic declarations and assessments, shared by the unit and contract suites.

Every party is obviously fictional and every address is an ``.example`` domain. One canonical
flagged declaration and one canonical clean declaration are enough for the contract suite: parity
means the SAME request through every implementation, so the request has one home rather than
being retyped per test.
"""

from __future__ import annotations

from conflicts_gifts_pad_register.domain.kernel import (
    Citation,
    Decision,
    Severity,
)
from conflicts_gifts_pad_register.domain.models import (
    AssessmentVerdict,
    ConflictAssessment,
    Declaration,
    DeclarationKind,
    Instrument,
    ScreeningFinding,
    ScreeningOutcome,
    ScreeningResult,
)

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "analyst@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: A second tenant, so the cross-tenant denial has a real "other" to be denied.
OTHER_TENANT = "other-bank"

#: The effective date the fixtures replay at (inside every seeded window).
AS_OF = "2026-08-08"

#: A planted identifier, so a redaction assertion has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"

#: A planted address, so the universal rows have an independent literal of their own.
PLANTED_EMAIL = "kai.tan@delta.example"

#: A declaration that MUST flag: a trader's gift over the SG threshold, so rule R8 routing
#: applies. It also carries a national id in the free text, for the redact-before-anything proof.
FLAGGED_DECLARATION = Declaration(
    id="dec-flagged",
    tenant=TENANT,
    employee="chen.trader@bank.example",
    employee_role="trader",
    market="SG",
    kind=DeclarationKind.GIFT,
    description=(
        f"Hamper from Vega Supplies (FICTIONAL); staff NRIC {PLANTED_NRIC} on the slip, "
        "reply-to vega.ops@vega.example"
    ),
    as_of=AS_OF,
    counterparty="Vega Supplies (FICTIONAL)",
    amount_minor=25000,
    currency="SGD",
)

#: The same declaration with the identifier in the register ID as well. The citation LOCATOR is
#: built from the declaration id (``declaration:<id>``, see ``ScreeningEngine.subject_citation``)
#: and the id is an unvalidated client string on the API request, so a redactor that masks only
#: the summary writes the identifier back into the WORM record from a field named like a key.
PII_LOCATOR_DECLARATION = Declaration(
    id=f"dec-{PLANTED_NRIC}",
    tenant=TENANT,
    employee="chen.trader@bank.example",
    employee_role="trader",
    market="SG",
    kind=DeclarationKind.GIFT,
    description=(
        f"Hamper from Vega Supplies (FICTIONAL); staff NRIC {PLANTED_NRIC} on the slip, "
        f"reply-to {PLANTED_EMAIL}"
    ),
    as_of=AS_OF,
    counterparty="Vega Supplies (FICTIONAL)",
    amount_minor=25000,
    currency="SGD",
)

#: A declaration that must NOT flag: an adviser's gift under the SG threshold.
CLEAN_DECLARATION = Declaration(
    id="dec-clean",
    tenant=TENANT,
    employee="lim.adviser@bank.example",
    employee_role="adviser",
    market="SG",
    kind=DeclarationKind.GIFT,
    description="Desk calendar from Nimbus Advisory (FICTIONAL), a token of thanks.",
    as_of=AS_OF,
    counterparty="Nimbus Advisory (FICTIONAL)",
    amount_minor=5000,
    currency="SGD",
)

#: A personal-account deal on a restricted symbol: the restricted-list detector must fire.
RESTRICTED_PAD = Declaration(
    id="pad-restricted",
    tenant=TENANT,
    employee="chen.trader@bank.example",
    employee_role="trader",
    market="SG",
    kind=DeclarationKind.PERSONAL_ACCOUNT_DEAL,
    description="Buy 100 FICT via personal broker account.",
    as_of=AS_OF,
    amount_minor=1500000,
    currency="SGD",
    instrument=Instrument(symbol="FICT", name="Fictus Holdings (FICTIONAL)"),
)

#: An adversarial near-miss: a symbol that LOOKS like the restricted one but is not it. The
#: restricted-list detector must NOT fire, which is what keeps screening precision at 1.0.
NEAR_MISS_PAD = Declaration(
    id="pad-near-miss",
    tenant=TENANT,
    employee="lim.adviser@bank.example",
    employee_role="adviser",
    market="SG",
    kind=DeclarationKind.PERSONAL_ACCOUNT_DEAL,
    description="Buy 100 FICTX via personal broker account.",
    as_of=AS_OF,
    amount_minor=900000,
    currency="SGD",
    instrument=Instrument(symbol="FICTX", name="Fictus Extra (FICTIONAL)"),
)

_CANONICAL_CITATION = Citation(
    source_id="declaration:dec-flagged",
    title="Declaration under screening",
    snippet="as_of 2026-08-08; 1 rule(s) fired",
)

#: The escalated assessment every review-router implementation is handed (rule R8's payload).
CANONICAL_ASSESSMENT = ConflictAssessment(
    declaration_id="dec-flagged",
    subject="chen.trader@bank.example / Vega Supplies (FICTIONAL)",
    employee="chen.trader@bank.example",
    tenant=TENANT,
    market="SG",
    kind=DeclarationKind.GIFT,
    verdict=AssessmentVerdict.ESCALATE,
    severity=Severity.HIGH,
    decision=Decision.ESCALATED,
    summary="gift declaration flagged as of 2026-08-08: gift_threshold. Verdict escalate.",
    screening=ScreeningResult(
        declaration_id="dec-flagged",
        outcome=ScreeningOutcome.FLAGGED,
        as_of=AS_OF,
        findings=(
            ScreeningFinding(
                rule_id="gift_threshold",
                reason="gift of 25000 SGD (minor units) exceeds the 10000 threshold",
                severity=Severity.HIGH,
            ),
        ),
    ),
    requires_human_review=True,
    citations=(_CANONICAL_CITATION,),
)
