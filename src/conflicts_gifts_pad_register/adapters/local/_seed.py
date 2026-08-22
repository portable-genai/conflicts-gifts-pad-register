"""Obviously fictional seed data for the offline profile (fixtures, tests, demo).

Every party, symbol and identifier here is invented: ``.example`` domains, ``FICTIONAL`` markers
and made-up ticker symbols. The dates sit inside the effective windows so a snapshot at
``AS_OF`` returns the whole set, which is what makes the demo and the tests deterministic.
"""

from __future__ import annotations

from ...domain.kernel import Citation
from ...domain.models import Declaration, DeclarationKind, Instrument
from ...domain.reference_models import (
    BlackoutWindow,
    EffectiveWindow,
    MnpiHolding,
    RestrictedSymbol,
)

#: The default effective date the demo and the offline gate replay at.
AS_OF = "2026-08-08"

TENANT = "demo-bank"
OTHER_TENANT = "other-bank"

_RESTRICTED_CITE = Citation(
    source_id="restricted:FICT",
    title="Restricted list entry (FICTIONAL)",
    snippet="Fictus Holdings restricted pending a fictional corporate action.",
)
_BLACKOUT_CITE = Citation(
    source_id="blackout:ZENX",
    title="Blackout calendar entry (FICTIONAL)",
    snippet="Zenith Example Bank results close period.",
)
_MNPI_CITE = Citation(
    source_id="mnpi:ORBX",
    title="MNPI holding entry (FICTIONAL)",
    snippet="Insider on a fictional deal team holds material non-public information.",
)

SEED_RESTRICTED: tuple[RestrictedSymbol, ...] = (
    RestrictedSymbol(
        symbol="FICT",
        reason="Fictus Holdings (FICTIONAL) restricted pending a corporate action",
        window=EffectiveWindow(effective_from="2026-01-01", effective_to="2026-12-31"),
        citation=_RESTRICTED_CITE,
    ),
)

SEED_BLACKOUTS: tuple[BlackoutWindow, ...] = (
    BlackoutWindow(
        symbol="ZENX",
        reason="Zenith Example Bank (FICTIONAL) results close period",
        window=EffectiveWindow(effective_from="2026-07-01", effective_to="2026-08-16"),
        citation=_BLACKOUT_CITE,
    ),
)

SEED_MNPI: tuple[MnpiHolding, ...] = (
    MnpiHolding(
        symbol="ORBX",
        insider="chen.trader@bank.example",
        reason="on a fictional deal team for Orbit Example Corp",
        window=EffectiveWindow(effective_from="2026-06-01", effective_to="2026-09-01"),
        citation=_MNPI_CITE,
    ),
)

#: Employee-submitted declarations (gifts, entertainment, interests, donations).
SEED_DECLARATIONS: tuple[Declaration, ...] = (
    Declaration(
        id="dec-gift-over",
        tenant=TENANT,
        employee="chen.trader@bank.example",
        employee_role="trader",
        market="SG",
        kind=DeclarationKind.GIFT,
        description=(
            "Hamper received from Vega Supplies (FICTIONAL) after a deal closed; "
            "contact vega.ops@vega.example"
        ),
        as_of=AS_OF,
        counterparty="Vega Supplies (FICTIONAL)",
        amount_minor=25000,
        currency="SGD",
    ),
    Declaration(
        id="dec-gift-under",
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
    ),
    Declaration(
        id="dec-interest",
        tenant=TENANT,
        employee="ng.analyst@bank.example",
        employee_role="analyst",
        market="SG",
        kind=DeclarationKind.OUTSIDE_INTEREST,
        description="Unpaid trustee of the Fictionalville Community Fund (FICTIONAL).",
        as_of=AS_OF,
        counterparty="Fictionalville Community Fund (FICTIONAL)",
    ),
)

#: Personal-account-dealing trades from the brokerage feed (already structured; no model).
SEED_PAD_TRADES: tuple[Declaration, ...] = (
    Declaration(
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
        instrument=Instrument(
            symbol="FICT", name="Fictus Holdings (FICTIONAL)", isin="XX0000000001"
        ),
    ),
    Declaration(
        id="pad-mnpi",
        tenant=TENANT,
        employee="chen.trader@bank.example",
        employee_role="trader",
        market="SG",
        kind=DeclarationKind.PERSONAL_ACCOUNT_DEAL,
        description="Buy 50 ORBX via personal broker account.",
        as_of=AS_OF,
        amount_minor=800000,
        currency="SGD",
        instrument=Instrument(
            symbol="ORBX", name="Orbit Example Corp (FICTIONAL)", isin="XX0000000002"
        ),
    ),
    Declaration(
        id="pad-clean",
        tenant=TENANT,
        employee="lim.adviser@bank.example",
        employee_role="adviser",
        market="SG",
        kind=DeclarationKind.PERSONAL_ACCOUNT_DEAL,
        description="Buy 200 CLNX via personal broker account.",
        as_of=AS_OF,
        amount_minor=400000,
        currency="SGD",
        instrument=Instrument(
            symbol="CLNX", name="Clean Example Ltd (FICTIONAL)", isin="XX0000000003"
        ),
    ),
)
