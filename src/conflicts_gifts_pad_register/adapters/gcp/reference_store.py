"""GCP ReferenceStorePort: BigQuery restricted / blackout / MNPI store (SDK imports stay lazy).

The managed reference store queries BigQuery in the residency region for every entry whose
effective window covers ``as_of`` and builds the same :class:`ReferenceSnapshot` shape the
offline adapter and the A2A endpoint serve. The SDK import is lazy, so the offline profiles
import this module with no GCP SDK installed.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.reference_models import (
    BlackoutWindow,
    MnpiHolding,
    ReferenceSnapshot,
    RestrictedSymbol,
)


class BigQueryReferenceStore:
    """Serve window-filtered reference snapshots from BigQuery."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def snapshot(self, as_of: str) -> ReferenceSnapshot:  # pragma: no cover - needs live GCP
        from google.cloud import bigquery

        _ = bigquery.Client()
        raise RuntimeError("BigQuery reference snapshot query is a deployment binding")

    def put_restricted(self, entry: RestrictedSymbol) -> None:  # pragma: no cover - live GCP
        from google.cloud import bigquery

        _ = bigquery.Client()
        raise RuntimeError("BigQuery reference writes are a deployment binding")

    def put_blackout(self, entry: BlackoutWindow) -> None:  # pragma: no cover - live GCP
        from google.cloud import bigquery

        _ = bigquery.Client()
        raise RuntimeError("BigQuery reference writes are a deployment binding")

    def put_mnpi(self, entry: MnpiHolding) -> None:  # pragma: no cover - live GCP
        from google.cloud import bigquery

        _ = bigquery.Client()
        raise RuntimeError("BigQuery reference writes are a deployment binding")
