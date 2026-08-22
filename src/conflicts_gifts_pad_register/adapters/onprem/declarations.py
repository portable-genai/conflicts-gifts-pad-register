"""On-prem declaration and brokerage feeds: fail-fast placeholders (sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import Declaration


class OnPremDeclarationFeed:
    """Satisfies DeclarationFeedPort but refuses: the client binds its own declaration system."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def declarations(self, tenant: str) -> tuple[Declaration, ...]:
        raise NotImplementedError(
            "on-prem declaration feed is a portability placeholder: bind the client's own "
            "declaration intake (see docs/onprem-migration.md)"
        )


class OnPremBrokerageFeed:
    """Satisfies BrokerageFeedPort but refuses: the client binds its own broker feed."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def pad_trades(self, tenant: str) -> tuple[Declaration, ...]:
        raise NotImplementedError(
            "on-prem brokerage feed is a portability placeholder: bind the client's own "
            "personal-account-dealing feed (see docs/onprem-migration.md)"
        )
