"""On-prem ReferenceStorePort: fail-fast portability placeholder (sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.reference_models import (
    BlackoutWindow,
    MnpiHolding,
    ReferenceSnapshot,
    RestrictedSymbol,
)

_MESSAGE = (
    "on-prem reference store is a portability placeholder: bind the client's own restricted-list "
    "/ blackout / MNPI system (see docs/onprem-migration.md)"
)


class OnPremReferenceStore:
    """Satisfies ReferenceStorePort but refuses: the client binds its own reference system."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def snapshot(self, as_of: str) -> ReferenceSnapshot:
        raise NotImplementedError(_MESSAGE)

    def put_restricted(self, entry: RestrictedSymbol) -> None:
        raise NotImplementedError(_MESSAGE)

    def put_blackout(self, entry: BlackoutWindow) -> None:
        raise NotImplementedError(_MESSAGE)

    def put_mnpi(self, entry: MnpiHolding) -> None:
        raise NotImplementedError(_MESSAGE)
