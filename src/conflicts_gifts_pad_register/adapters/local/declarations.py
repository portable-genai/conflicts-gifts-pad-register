"""Local declaration and brokerage feeds: SDK-free fixtures of obviously fictional parties.

The offline stand-ins for the managed feeds. The declaration feed serves employee-submitted
gifts / entertainment / interests / donations; the brokerage feed serves personal-account-dealing
trades. Both are tenant-filtered so the offline profile exercises the same tenant boundary the
managed one enforces.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import Declaration
from ._seed import SEED_DECLARATIONS, SEED_PAD_TRADES


class LocalDeclarationFeed:
    """Serve seeded employee declarations for the ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def declarations(self, tenant: str) -> tuple[Declaration, ...]:
        if not tenant:
            return ()
        return tuple(d for d in SEED_DECLARATIONS if d.tenant == tenant)


class LocalBrokerageFeed:
    """Serve seeded personal-account-dealing trades for the ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def pad_trades(self, tenant: str) -> tuple[Declaration, ...]:
        if not tenant:
            return ()
        return tuple(d for d in SEED_PAD_TRADES if d.tenant == tenant)
