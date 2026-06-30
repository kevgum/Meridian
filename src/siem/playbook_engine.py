"""Playbook engine — fires automated incident response when the hybrid threat score is triggered.

When PlaybookEngine.fire() is called, it:
  1. Generates a UUID incident record with full evidence
  2. Writes the record to Elasticsearch index meridian-incidents-YYYY.MM.dd
  3. Emits a mock analyst notification via the Python logger

In production the notification would POST to a Teams/PagerDuty webhook.
For the prototype the log line at WARNING level serves as the audit evidence.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Lazy-import Elasticsearch so the module can be imported without the package
# installed — tests that mock the client never trigger the real import path.
try:
    from elasticsearch import Elasticsearch
    _ES_AVAILABLE = True
except ImportError:
    _ES_AVAILABLE = False
    Elasticsearch = Any  # type: ignore[misc,assignment]

# Index prefix — daily rollover appended at write time: meridian-incidents-2026.06.30
_INCIDENT_INDEX_PREFIX = "meridian-incidents"


def _severity_from_score(threat_score: float, trigger_reason: str) -> str:
    """Map a threat score and trigger reason to a severity label.

    Scores >= 0.90 are CRITICAL (high-confidence automated detection).
    LSTM_ALONE triggers are HIGH — strong behavioural signal, no SIEM corroboration.
    Everything else that crossed the threshold is HIGH.
    """
    if threat_score >= 0.90:
        return "CRITICAL"
    # LSTM_ALONE and HYBRID_THRESHOLD below 0.90 are both HIGH
    return "HIGH"


class PlaybookEngine:
    """Executes the automated incident response playbook for flagged transactions.

    Generates an incident record, persists it to Elasticsearch, and sends a
    mock analyst notification.  The Elasticsearch client is injected at
    construction to allow unit tests to pass a MagicMock without hitting a
    live cluster.

    Usage::

        engine = PlaybookEngine()           # builds ES client from env vars
        incident = engine.fire(payload)     # payload from HybridThreatScorer.score()

    For tests::

        mock_es = MagicMock()
        engine = PlaybookEngine(es_client=mock_es)
    """

    def __init__(self, es_client: Any | None = None) -> None:
        """Initialise the engine with an optional pre-built ES client.

        Args:
            es_client: An Elasticsearch client instance.  If None, one is
                       built from the ELASTIC_HOST and ELASTIC_PASSWORD
                       environment variables.  Pass a MagicMock in tests.
        """
        if es_client is not None:
            self._es = es_client
        elif _ES_AVAILABLE:
            self._es = self._build_client()
        else:
            # elasticsearch package not installed — log-only mode
            self._es = None
            logger.warning(
                "elasticsearch package not installed; incidents will be logged only"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fire(self, scorer_result: dict) -> dict:
        """Execute the playbook and return the incident record.

        Args:
            scorer_result: The dict returned by HybridThreatScorer.score().
                           Must include: threat_score, lstm_score, siem_score,
                           trigger_reason, siem_rules, event.

        Returns:
            The full incident dict that was written to Elasticsearch.
        """
        incident = self._build_incident(scorer_result)
        self._write_to_elasticsearch(incident)
        self._notify_analyst(incident)
        return incident

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_incident(self, scorer_result: dict) -> dict:
        """Construct the incident payload from scorer output.

        The incident ID is a UUID4 so records are globally unique and
        can be correlated across services without a central counter.
        """
        threat_score = scorer_result.get("threat_score", 0.0)
        trigger_reason = scorer_result.get("trigger_reason", "UNKNOWN")
        event = scorer_result.get("event", {})

        # Extract customer ID from the ECS-normalised event field if available,
        # falling back to a raw field for events not yet processed by Logstash
        customer_id = (
            event.get("source", {}).get("user", {}).get("id")
            or event.get("customer_id")
            or event.get("nameOrig", "UNKNOWN")
        )

        # Collect transaction evidence fields for analyst review
        evidence: dict = {
            "amount": event.get("amount"),
            "merchant_id": event.get("merchant_id"),
            "timestamp": event.get("timestamp"),
            "lat": event.get("lat"),
            "lon": event.get("lon"),
        }

        return {
            "incident_id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "action": "LOCK_ACCOUNT",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "threat_score": round(threat_score, 4),
            "lstm_score": round(scorer_result.get("lstm_score", 0.0), 4),
            "siem_score": round(scorer_result.get("siem_score", 0.0), 4),
            "trigger_reason": trigger_reason,
            "severity": _severity_from_score(threat_score, trigger_reason),
            "siem_rules": scorer_result.get("siem_rules", []),
            "evidence": evidence,
            "status": "OPEN",
            "analyst_assigned": None,
        }

    def _write_to_elasticsearch(self, incident: dict) -> None:
        """Index the incident document into a daily Elasticsearch index.

        Index pattern: meridian-incidents-YYYY.MM.dd
        Silently skips if the ES client is unavailable (log-only mode).
        """
        if self._es is None:
            return

        # Daily index rollover keeps index sizes manageable and supports
        # time-based retention policies required by PCI DSS Requirement 10.7
        today = datetime.now(tz=timezone.utc).strftime("%Y.%m.%d")
        index_name = f"{_INCIDENT_INDEX_PREFIX}-{today}"

        try:
            self._es.index(index=index_name, document=incident)
            logger.info("Incident %s written to %s", incident["incident_id"], index_name)
        except Exception as exc:  # noqa: BLE001
            # Log but do not re-raise — a failed ES write must not suppress the
            # analyst notification or prevent the incident dict being returned
            logger.error(
                "Failed to write incident %s to Elasticsearch: %s",
                incident["incident_id"],
                exc,
            )

    def _notify_analyst(self, incident: dict) -> None:
        """Send an analyst notification for the incident.

        Prototype: emits a structured WARNING log that monitoring agents
        (Logstash, Filebeat) can pick up and forward to the Teams channel.
        Production: replace with a POST to the Teams/PagerDuty webhook URL
        stored in the ANALYST_WEBHOOK_URL environment variable.
        """
        logger.warning(
            "INCIDENT CREATED | id=%s | customer=%s | severity=%s | "
            "threat_score=%.4f | trigger=%s | action=%s",
            incident["incident_id"],
            incident["customer_id"],
            incident["severity"],
            incident["threat_score"],
            incident["trigger_reason"],
            incident["action"],
        )

    @staticmethod
    def _build_client() -> "Elasticsearch":
        """Build an Elasticsearch client from environment variables.

        Reads ELASTIC_HOST (default http://elasticsearch:9200) and
        ELASTIC_PASSWORD (default meridian123).  Credentials must never
        be hardcoded — they are injected via .env / Docker environment.
        """
        host = os.environ.get("ELASTIC_HOST", "http://elasticsearch:9200")
        password = os.environ.get("ELASTIC_PASSWORD", "meridian123")
        return Elasticsearch(host, basic_auth=("elastic", password))
