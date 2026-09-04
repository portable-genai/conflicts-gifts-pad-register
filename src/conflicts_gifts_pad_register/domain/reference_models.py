"""The restricted-list / blackout-window / MNPI reference model (pure stdlib).

This is the reference data trade-comms-surveillance (``trade-comms-surveillance``) reads over A2A,
so its shape is authoritative here: the OWNER of the data owns its schema. Every entry carries an
effective window, and a :class:`ReferenceSnapshot` is the set of entries whose window COVERS a given
``as_of`` date. Replaying the same ``as_of`` therefore reproduces the same snapshot byte for byte,
which is what makes screening reproducible and an audit defensible.

Nothing here imports a web framework or a cloud SDK: a snapshot is a value the deterministic
engine reasons over, and the store adapter (``ports/reference_store.py``) is the only thing that
knows where the entries physically live.
"""

from __future__ import annotations

from dataclasses import dataclass

from .kernel import Citation


@dataclass(frozen=True, slots=True)
class EffectiveWindow:
    """A closed-open effective window on ``YYYY-MM-DD`` dates. Empty bound means open-ended.

    Comparison is lexicographic on ISO dates, which is why the format is fixed: an ISO date
    sorts the same as the calendar date it names, so no date parsing is needed in the hot path
    and the result is deterministic.
    """

    effective_from: str = ""
    effective_to: str = ""

    def covers(self, as_of: str) -> bool:
        if self.effective_from and as_of < self.effective_from:
            return False
        return not (self.effective_to and as_of >= self.effective_to)


@dataclass(frozen=True, slots=True)
class RestrictedSymbol:
    """A symbol on the restricted list for an effective window, with its reason and source."""

    symbol: str
    reason: str
    window: EffectiveWindow
    citation: Citation | None = None

    @property
    def identity(self) -> str:
        return self.symbol.strip().upper()


@dataclass(frozen=True, slots=True)
class BlackoutWindow:
    """A dealing blackout on a symbol for an effective window (e.g. a results close period)."""

    symbol: str
    reason: str
    window: EffectiveWindow
    citation: Citation | None = None

    @property
    def identity(self) -> str:
        return self.symbol.strip().upper()


@dataclass(frozen=True, slots=True)
class MnpiHolding:
    """An insider's material-non-public-information holding on a symbol, for a window."""

    symbol: str
    insider: str
    reason: str
    window: EffectiveWindow
    citation: Citation | None = None

    @property
    def identity(self) -> str:
        return self.symbol.strip().upper()


@dataclass(frozen=True, slots=True)
class ReferenceSnapshot:
    """The reference data effective at one ``as_of`` date: the atom trade-comms-surveillance reads
    and screening uses.

    Constructed already filtered to ``as_of`` by :meth:`from_entries`, so the lookups below are
    exact-match membership and never re-check a window. That keeps the byte-identical replay
    property: two snapshots at the same ``as_of`` over the same store are equal.
    """

    as_of: str
    restricted: tuple[RestrictedSymbol, ...] = ()
    blackouts: tuple[BlackoutWindow, ...] = ()
    mnpi: tuple[MnpiHolding, ...] = ()

    @classmethod
    def from_entries(
        cls,
        as_of: str,
        restricted: tuple[RestrictedSymbol, ...],
        blackouts: tuple[BlackoutWindow, ...],
        mnpi: tuple[MnpiHolding, ...],
    ) -> ReferenceSnapshot:
        """Keep only entries whose window covers ``as_of``, sorted for a stable wire form."""
        return cls(
            as_of=as_of,
            restricted=tuple(
                sorted((r for r in restricted if r.window.covers(as_of)), key=lambda r: r.identity)
            ),
            blackouts=tuple(
                sorted((b for b in blackouts if b.window.covers(as_of)), key=lambda b: b.identity)
            ),
            mnpi=tuple(
                sorted(
                    (m for m in mnpi if m.window.covers(as_of)),
                    key=lambda m: (m.identity, m.insider),
                )
            ),
        )

    def is_restricted(self, symbol: str) -> RestrictedSymbol | None:
        key = symbol.strip().upper()
        return next((r for r in self.restricted if r.identity == key), None)

    def in_blackout(self, symbol: str) -> BlackoutWindow | None:
        key = symbol.strip().upper()
        return next((b for b in self.blackouts if b.identity == key), None)

    def mnpi_for(self, symbol: str, insider: str) -> MnpiHolding | None:
        key = symbol.strip().upper()
        return next(
            (m for m in self.mnpi if m.identity == key and m.insider == insider),
            None,
        )
