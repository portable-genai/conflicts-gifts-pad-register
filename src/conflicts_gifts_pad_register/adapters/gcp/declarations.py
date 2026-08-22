"""GCP declaration and brokerage feeds: Document AI / BigQuery (SDK imports stay lazy).

The managed feeds read employee declarations (free text extracted by Document AI, structured
fields from BigQuery) and personal-account-dealing trades (BigQuery). Every SDK import lives
inside the method so the offline profiles import this module with no GCP SDK installed.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import Declaration


class BigQueryDeclarationFeed:
    """Read employee declarations from BigQuery in the residency region."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def declarations(self, tenant: str) -> tuple[Declaration, ...]:  # pragma: no cover - live GCP
        from google.cloud import bigquery

        _ = bigquery.Client()
        raise RuntimeError("BigQuery declaration feed query is a deployment binding")


class BigQueryBrokerageFeed:
    """Read personal-account-dealing trades from BigQuery in the residency region."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def pad_trades(self, tenant: str) -> tuple[Declaration, ...]:  # pragma: no cover - live GCP
        from google.cloud import bigquery

        _ = bigquery.Client()
        raise RuntimeError("BigQuery brokerage feed query is a deployment binding")
