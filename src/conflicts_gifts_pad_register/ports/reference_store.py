"""ReferenceStorePort: the restricted-list / blackout / MNPI store, the data
trade-comms-surveillance reads.

conflicts-gifts-pad-register OWNS this reference data, so it owns its schema:
trade-comms-surveillance (``trade-comms-surveillance``) consumes an ``as_of`` snapshot of it over
A2A and its adapter conforms to what this port produces. Every entry carries an effective window,
and :meth:`snapshot` returns exactly the entries whose window covers a given date, so replaying the
same ``as_of`` reproduces the same snapshot byte for byte.

The ``gcp`` adapter is BigQuery in the residency region; the ``local`` adapter is an SDK-free
in-memory store seeded with obviously fictional entries; the ``onprem`` adapter fails fast.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.reference_models import (
    BlackoutWindow,
    MnpiHolding,
    ReferenceSnapshot,
    RestrictedSymbol,
)


@runtime_checkable
class ReferenceStorePort(Protocol):
    def snapshot(self, as_of: str) -> ReferenceSnapshot:
        """Return the reference data effective at ``as_of`` (window-filtered, deterministic)."""
        ...

    def put_restricted(self, entry: RestrictedSymbol) -> None:
        """Add or replace a restricted-list entry."""
        ...

    def put_blackout(self, entry: BlackoutWindow) -> None:
        """Add or replace a blackout-window entry."""
        ...

    def put_mnpi(self, entry: MnpiHolding) -> None:
        """Add or replace an MNPI-holding entry."""
        ...
