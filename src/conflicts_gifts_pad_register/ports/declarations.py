"""DeclarationFeedPort and BrokerageFeedPort: the inbound edges the register ingests from.

Two feeds, deliberately separate because they come from different systems in a real deployment:

* :class:`DeclarationFeedPort` serves employee-submitted declarations (gifts and entertainment,
  outside business interests, political donations), which arrive as free text plus structured
  fields, so the ``gcp`` adapter is Document AI plus BigQuery and the model resolves the entity.
* :class:`BrokerageFeedPort` serves personal-account-dealing trades and holdings from a broker
  feed, which are already structured, so no model touches them; the deterministic normaliser
  owns the instrument identity, amount and date.

Both return domain :class:`~conflicts_gifts_pad_register.domain.models.Declaration` values, so
the ingestion and screening pipeline is feed-agnostic. The ``local`` adapters are SDK-free
fixtures of obviously fictional parties; the ``onprem`` adapters fail fast.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import Declaration


@runtime_checkable
class DeclarationFeedPort(Protocol):
    def declarations(self, tenant: str) -> tuple[Declaration, ...]:
        """Return the employee declarations awaiting screening for ``tenant``."""
        ...


@runtime_checkable
class BrokerageFeedPort(Protocol):
    def pad_trades(self, tenant: str) -> tuple[Declaration, ...]:
        """Return the personal-account-dealing trades awaiting screening for ``tenant``."""
        ...
