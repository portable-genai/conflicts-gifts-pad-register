"""Loader for the screening threshold pack (config into domain values).

Lives OUTSIDE ``domain/`` because it reads YAML from disk, and the domain core stays pure
stdlib with no I/O. It turns the reference pack shipped at
``conflicts_gifts_pad_register/rulepacks/screening.yaml`` (or an adopter's own file, selected
by ``screening_pack_path`` in ``config/settings.yaml``) into one immutable
:class:`ScreeningPack` value the screening engine takes as a parameter.

Why a pack file rather than constants in the engine: the per-role, per-market gift and
entertainment thresholds are the ADOPTER's policy, not an algorithm (practice B4). A compliance
officer tunes them, or adds a market, by editing config a human can read and diff; the engine
never learns a role's name or a currency.

Loading is fail-closed: an unreadable file, an unknown declaration kind, a limit that cites a
citation id the pack does not define, or a limit with no threshold raises
:class:`ScreeningPackError`. A screening gate running on a silently empty or partly-parsed pack
would wave conflicts through, so it must not start at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .domain.errors import ScreeningPackError
from .domain.kernel import Citation, Severity
from .domain.models import DeclarationKind

DEFAULT_PACK_PATH = Path(__file__).resolve().parent / "rulepacks" / "screening.yaml"

#: The declaration kinds a gift/entertainment threshold may target. A threshold on an
#: instrument-only kind (a personal-account deal) is a config error, because those are screened
#: against the restricted list and the blackout calendar, not against a monetary limit.
_THRESHOLD_KINDS = (DeclarationKind.GIFT, DeclarationKind.ENTERTAINMENT)


@dataclass(frozen=True, slots=True)
class GiftLimit:
    """One per-role, per-market threshold for a gift or entertainment declaration."""

    role: str
    market: str
    kind: DeclarationKind
    threshold_minor: int
    currency: str
    severity: Severity
    citation: Citation
    remediation: str = ""


@dataclass(frozen=True, slots=True)
class ScreeningPack:
    """The immutable set of screening thresholds, keyed by (role, market, kind)."""

    version: str
    limits: dict[tuple[str, str, DeclarationKind], GiftLimit]

    def gift_limit(self, role: str, market: str, kind: DeclarationKind) -> GiftLimit | None:
        """The configured threshold for this role/market/kind, or ``None`` when none is set.

        ``None`` means the test is UNCONFIGURED for this combination. The engine treats that as
        a gap to flag for review, never as a pass: an unconfigured test is not a clean one.
        """
        return self.limits.get((role, market, kind))


def _fail(message: str) -> Any:
    raise ScreeningPackError(f"screening pack: {message}")


def _enum(cls: Any, value: Any, what: str) -> Any:
    try:
        return cls(str(value))
    except ValueError:
        permitted = ", ".join(sorted(m.value for m in cls))
        return _fail(f"unknown {what} {value!r}; permitted: {permitted}")


def _citations(doc: dict[str, Any]) -> dict[str, Citation]:
    raw = doc.get("citations") or {}
    if not isinstance(raw, dict) or not raw:
        _fail("no 'citations' block; every threshold must name the instrument it comes from")
    out: dict[str, Citation] = {}
    for citation_id, spec in raw.items():
        if not isinstance(spec, dict) or not str(spec.get("title", "")).strip():
            _fail(f"citation {citation_id!r} has no title (a citation must name its instrument)")
        out[str(citation_id)] = Citation(
            source_id=str(citation_id),
            title=str(spec.get("title", "")).strip(),
            snippet=" ".join(str(spec.get("snippet", "")).split()),
        )
    return out


def _limits(
    doc: dict[str, Any], citations: dict[str, Citation]
) -> dict[tuple[str, str, DeclarationKind], GiftLimit]:
    raw = doc.get("thresholds") or []
    if not isinstance(raw, list) or not raw:
        _fail("no 'thresholds' block; a pack with no thresholds screens nothing")
    out: dict[tuple[str, str, DeclarationKind], GiftLimit] = {}
    for spec in raw:
        if not isinstance(spec, dict):
            _fail("each threshold must be a mapping")
        role = str(spec.get("role", "")).strip()
        market = str(spec.get("market", "")).strip()
        if not role or not market:
            _fail("a threshold needs both a 'role' and a 'market'")
        kind = _enum(DeclarationKind, spec.get("kind", ""), "declaration kind")
        if kind not in _THRESHOLD_KINDS:
            permitted = ", ".join(k.value for k in _THRESHOLD_KINDS)
            _fail(f"threshold kind {kind.value!r} is not monetary; use one of {permitted}")
        if "threshold_minor" not in spec:
            _fail(f"{role}/{market}/{kind.value}: no 'threshold_minor' (a limit must be a number)")
        citation_id = str(spec.get("citation", "") or "")
        if citation_id not in citations:
            _fail(
                f"{role}/{market}/{kind.value}: citation {citation_id!r} is not defined in the "
                "pack; every threshold must state a named policy instrument"
            )
        out[(role, market, kind)] = GiftLimit(
            role=role,
            market=market,
            kind=kind,
            threshold_minor=int(spec["threshold_minor"]),
            currency=str(spec.get("currency", "")).strip(),
            severity=_enum(Severity, spec.get("severity", "medium"), "severity"),
            citation=citations[citation_id],
            remediation=" ".join(str(spec.get("remediation", "")).split()),
        )
    return out


def load_pack(path: str | Path | None = None) -> ScreeningPack:
    """Load and validate a screening pack from ``path`` (default: the reference pack)."""
    pack_path = Path(path) if path else DEFAULT_PACK_PATH
    if not pack_path.exists():
        _fail(f"pack file {pack_path} does not exist; screening cannot run without it")
    try:
        doc = yaml.safe_load(pack_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ScreeningPackError(f"screening pack: {pack_path} is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        _fail(f"{pack_path} must contain a mapping")
    citations = _citations(doc)
    return ScreeningPack(version=str(doc.get("version", "")), limits=_limits(doc, citations))


@lru_cache(maxsize=4)
def _cached_pack(resolved: str) -> ScreeningPack:
    return load_pack(resolved)


def pack_for(pack_path: str = "") -> ScreeningPack:
    """Resolve the active pack (adopter override, else the reference)."""
    return _cached_pack(pack_path.strip() or str(DEFAULT_PACK_PATH))
