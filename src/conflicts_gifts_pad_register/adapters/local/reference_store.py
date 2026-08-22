"""Local ReferenceStorePort: an SDK-free in-memory restricted / blackout / MNPI store.

The offline stand-in for the managed reference store (BigQuery on GCP). It holds every entry with
its effective window and builds a :class:`ReferenceSnapshot` for a given ``as_of`` by keeping
only the entries whose window covers that date, so replaying the same ``as_of`` reproduces the
same snapshot byte for byte. This is the data Cmp1 reads over A2A, so the offline adapter and the
A2A endpoint serve exactly the same shape.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.reference_models import (
    BlackoutWindow,
    MnpiHolding,
    ReferenceSnapshot,
    RestrictedSymbol,
)
from ._seed import SEED_BLACKOUTS, SEED_MNPI, SEED_RESTRICTED


class LocalReferenceStore:
    """Serve tenant-neutral, window-filtered reference snapshots from a seeded in-memory store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._restricted: dict[str, RestrictedSymbol] = {r.identity: r for r in SEED_RESTRICTED}
        self._blackouts: dict[str, BlackoutWindow] = {b.identity: b for b in SEED_BLACKOUTS}
        self._mnpi: dict[tuple[str, str], MnpiHolding] = {
            (m.identity, m.insider): m for m in SEED_MNPI
        }

    def snapshot(self, as_of: str) -> ReferenceSnapshot:
        return ReferenceSnapshot.from_entries(
            as_of=as_of,
            restricted=tuple(self._restricted.values()),
            blackouts=tuple(self._blackouts.values()),
            mnpi=tuple(self._mnpi.values()),
        )

    def put_restricted(self, entry: RestrictedSymbol) -> None:
        self._restricted[entry.identity] = entry

    def put_blackout(self, entry: BlackoutWindow) -> None:
        self._blackouts[entry.identity] = entry

    def put_mnpi(self, entry: MnpiHolding) -> None:
        self._mnpi[(entry.identity, entry.insider)] = entry
