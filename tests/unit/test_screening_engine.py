"""The deterministic screening engine: which rules fire, replayable from the as-of snapshot.

The engine owns every consequential decision (which rules fired, CLEAR / FLAGGED, severity), so
these tests are the ones that hold the line the whole service rests on. They cover each detector,
the exact-match that keeps an adversarial near-miss out, the fail-closed unconfigured threshold,
and the effective-window replay that makes an as-of screening reproducible.
"""

from __future__ import annotations

from conflicts_gifts_pad_register.adapters.local.llm import LocalLlmAdapter
from conflicts_gifts_pad_register.adapters.local.reference_store import LocalReferenceStore
from conflicts_gifts_pad_register.config import Settings
from conflicts_gifts_pad_register.domain.ingestion_service import IngestionService
from conflicts_gifts_pad_register.domain.kernel import Severity
from conflicts_gifts_pad_register.domain.models import ScreeningOutcome
from conflicts_gifts_pad_register.domain.screening_engine import ScreeningEngine
from conflicts_gifts_pad_register.screening_pack import pack_for

from tests.fixtures import sample_cases

_SETTINGS = Settings(profile="local")
_INGESTION = IngestionService(LocalLlmAdapter(_SETTINGS))
_STORE = LocalReferenceStore(_SETTINGS)
_PACK = pack_for()
_ENGINE = ScreeningEngine()


def _screen(declaration: object, as_of: str = sample_cases.AS_OF) -> object:
    normalized = _INGESTION.normalize(declaration)  # type: ignore[arg-type]
    return _ENGINE.screen(normalized, _STORE.snapshot(as_of), _PACK)


def _fired(result: object) -> set[str]:
    return {f.rule_id for f in result.findings}  # type: ignore[attr-defined]


def test_a_gift_over_threshold_flags_on_the_gift_rule() -> None:
    result = _screen(sample_cases.FLAGGED_DECLARATION)
    assert result.outcome is ScreeningOutcome.FLAGGED  # type: ignore[attr-defined]
    assert "gift_threshold" in _fired(result)


def test_a_gift_under_threshold_clears() -> None:
    result = _screen(sample_cases.CLEAN_DECLARATION)
    assert result.outcome is ScreeningOutcome.CLEAR  # type: ignore[attr-defined]
    assert _fired(result) == set()


def test_a_restricted_symbol_flags_and_a_near_miss_does_not() -> None:
    """Exact match on the instrument identity: precision at 1.0 over the adversarial pair."""
    assert "restricted_list" in _fired(_screen(sample_cases.RESTRICTED_PAD))
    assert "restricted_list" not in _fired(_screen(sample_cases.NEAR_MISS_PAD))


def test_the_wildcard_mutant_would_flag_the_near_miss() -> None:
    """The proof that the exact-match matters: relax it and the near-miss becomes a false hit."""
    wildcard = ScreeningEngine(match_any=True)
    normalized = _INGESTION.normalize(sample_cases.NEAR_MISS_PAD)
    result = wildcard.screen(normalized, _STORE.snapshot(sample_cases.AS_OF), _PACK)
    assert "restricted_list" in {f.rule_id for f in result.findings}


def test_an_unconfigured_threshold_is_a_gap_not_a_pass() -> None:
    """Fail closed: a role/market with no configured limit flags for review rather than clearing."""
    from conflicts_gifts_pad_register.domain.models import Declaration, DeclarationKind

    unknown_market = Declaration(
        id="dec-unknown",
        tenant="demo-bank",
        employee="x@bank.example",
        employee_role="trader",
        market="ZZ",  # no threshold configured for this market
        kind=DeclarationKind.GIFT,
        description="Gift from Somebody (FICTIONAL)",
        as_of=sample_cases.AS_OF,
        amount_minor=100,
        currency="SGD",
    )
    result = _screen(unknown_market)
    assert result.outcome is ScreeningOutcome.FLAGGED  # type: ignore[attr-defined]
    assert "gift_threshold_unconfigured" in _fired(result)


def test_the_mnpi_detector_is_the_most_severe() -> None:
    from conflicts_gifts_pad_register.domain.models import Declaration, DeclarationKind, Instrument

    mnpi = Declaration(
        id="pad-mnpi",
        tenant="demo-bank",
        employee="chen.trader@bank.example",
        employee_role="trader",
        market="SG",
        kind=DeclarationKind.PERSONAL_ACCOUNT_DEAL,
        description="Buy 50 ORBX via personal broker account.",
        as_of=sample_cases.AS_OF,
        amount_minor=800000,
        currency="SGD",
        instrument=Instrument(symbol="ORBX"),
    )
    result = _screen(mnpi)
    assert "mnpi_conflict" in _fired(result)
    assert ScreeningEngine.worst_severity(result) is Severity.CRITICAL  # type: ignore[arg-type]


def test_as_of_replay_is_reproducible_and_window_bounded() -> None:
    """Outside the blackout window the blackout rule must not fire; inside it, it must."""
    from conflicts_gifts_pad_register.domain.models import Declaration, DeclarationKind, Instrument

    zenx = Declaration(
        id="pad-zenx",
        tenant="demo-bank",
        employee="x@bank.example",
        employee_role="trader",
        market="SG",
        kind=DeclarationKind.PERSONAL_ACCOUNT_DEAL,
        description="Buy 10 ZENX via personal broker account.",
        as_of=sample_cases.AS_OF,
        amount_minor=1000,
        currency="SGD",
        instrument=Instrument(symbol="ZENX"),
    )
    inside = _screen(zenx, as_of="2026-08-08")  # inside the 2026-07-01..2026-08-16 window
    outside = _screen(zenx, as_of="2026-09-01")  # after the window closes
    assert "blackout_window" in _fired(inside)
    assert "blackout_window" not in _fired(outside)
