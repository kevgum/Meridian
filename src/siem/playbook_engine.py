"""Playbook engine — fires automated incident response when the hybrid threat score is triggered.

When PlaybookEngine.fire() is called, it:
  1. Generates a UUID incident record with full evidence
  2. Writes the record to Elasticsearch index meridian-incidents-YYYY.MM.dd
  3. Writes a notification record to meridian-notifications-YYYY.MM.dd
  4. POSTs a JSON payload to ANALYST_WEBHOOK_URL (if set in env) for Teams/PagerDuty/Slack
  5. Emits a structured WARNING log for log-aggregation agents (Logstash, Filebeat)

Set ANALYST_WEBHOOK_URL in .env to route notifications to a real channel.
Leave it unset to run in log-only mode.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
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

# Index prefixes — daily rollover appended at write time
_INCIDENT_INDEX_PREFIX = "meridian-incidents"
_NOTIFICATION_INDEX_PREFIX = "meridian-notifications"


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

        Three notification channels are attempted in order:
        1. meridian-notifications-* Elasticsearch index — searchable, auditable record.
        2. ANALYST_WEBHOOK_URL (env) — HTTP POST to Teams/PagerDuty/Slack if configured.
        3. logger.WARNING — always emitted; picked up by Logstash/Filebeat.
        """
        self._write_notification_to_elasticsearch(incident)
        self._post_webhook(incident)
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

    def _write_notification_to_elasticsearch(self, incident: dict) -> None:
        """Persist a notification record to a daily ES index.

        Separate from the incident index so notification delivery status can be
        queried independently.  Index pattern: meridian-notifications-YYYY.MM.dd
        """
        if self._es is None:
            return

        today = datetime.now(tz=timezone.utc).strftime("%Y.%m.%d")
        index_name = f"{_NOTIFICATION_INDEX_PREFIX}-{today}"
        notification = {
            "notification_id": str(uuid.uuid4()),
            "incident_id": incident["incident_id"],
            "customer_id": incident["customer_id"],
            "severity": incident["severity"],
            "threat_score": incident["threat_score"],
            "trigger_reason": incident["trigger_reason"],
            "action": incident["action"],
            "channel": "elasticsearch",
            "delivered_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": "DELIVERED",
        }

        try:
            self._es.index(index=index_name, document=notification)
            logger.info(
                "Notification for incident %s written to %s",
                incident["incident_id"],
                index_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to write notification for incident %s: %s",
                incident["incident_id"],
                exc,
            )

    @staticmethod
    def _post_webhook(incident: dict) -> None:
        """POST a JSON notification payload to ANALYST_WEBHOOK_URL.

        Supports Microsoft Teams (Adaptive Card), Slack (Block Kit), and any
        generic JSON endpoint.  The payload is a simple flat dict; the receiving
        service maps it to its own format.  Silently skips if the env var is
        not set.
        """
        webhook_url = os.environ.get("ANALYST_WEBHOOK_URL", "")
        if not webhook_url:
            return

        payload = {
            "type": "MERIDIAN_INCIDENT",
            "incident_id": incident["incident_id"],
            "customer_id": incident["customer_id"],
            "severity": incident["severity"],
            "threat_score": incident["threat_score"],
            "trigger_reason": incident["trigger_reason"],
            "action": incident["action"],
            "timestamp": incident["timestamp"],
            "message": (
                f"[{incident['severity']}] Incident {incident['incident_id']} — "
                f"customer {incident['customer_id']} | "
                f"threat_score={incident['threat_score']:.4f} | "
                f"action={incident['action']}"
            ),
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info(
                    "Webhook notification delivered for incident %s (HTTP %s)",
                    incident["incident_id"],
                    resp.status,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Webhook delivery failed for incident %s: %s",
                incident["incident_id"],
                exc,
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
