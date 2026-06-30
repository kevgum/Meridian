"""Hybrid threat scorer — fuses LSTM anomaly probability and SIEM rule score
into a single threat metric and triggers the automated playbook when warranted.

Blending formula (from architecture spec):
    threat_score = (lstm_score × 0.60) + (siem_score × 0.40)

Trigger conditions (dual-threshold design):
    HYBRID_THRESHOLD  — threat_score >= 0.70: both signals combine to flag
    LSTM_ALONE        — lstm_score >= 0.70 even when siem_score == 0.00:
                        strong behavioural anomaly with no SIEM corroboration,
                        e.g. CUST-18656 where all 4 SIEM rules pass but LSTM
                        returns 0.74 (hybrid would only be 0.44 without this path)

Below both thresholds the transaction is placed in MONITOR state.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Avoid circular import at runtime; PlaybookEngine is only referenced in
    # type hints and constructor signature
    from .playbook_engine import PlaybookEngine

logger = logging.getLogger(__name__)

# Architecture-specified weights for the two detection engines
_LSTM_WEIGHT: float = 0.60
_SIEM_WEIGHT: float = 0.40

# Threat score above which the playbook fires (HYBRID_THRESHOLD path)
_HYBRID_THRESHOLD: float = 0.70

# LSTM score above which the playbook fires even with siem_score == 0
# (LSTM_ALONE path — preserves the CUST-18656 scenario)
_LSTM_ALONE_THRESHOLD: float = 0.70


class HybridThreatScorer:
    """Blends LSTM anomaly probability and SIEM rule score into a single verdict.

    Designed for use with ElasticSIEMCorrelator (src/siem/rule_engine.py) and
    LSTMInferenceClient (src/inference_client.py).  The PlaybookEngine is
    injected at construction so that tests can substitute a mock without
    needing a running Elasticsearch cluster.

    Usage::

        from src.siem.hybrid_scorer import HybridThreatScorer
        from src.siem.playbook_engine import PlaybookEngine

        engine = PlaybookEngine()
        scorer = HybridThreatScorer(playbook_engine=engine)
        result = scorer.score(lstm_score=0.74, siem_result=siem_output, event=event)
        # result["verdict"]         → "FLAGGED" or "MONITOR"
        # result["trigger_reason"]  → "HYBRID_THRESHOLD", "LSTM_ALONE", or "NONE"
        # result["incident"]        → incident dict if playbook fired, else None

    For tests (no live services)::

        from unittest.mock import MagicMock
        scorer = HybridThreatScorer(playbook_engine=MagicMock())
        result = scorer.score(0.74, {"siem_score": 0.00, "rules": []}, {})
    """

    def __init__(self, playbook_engine: "PlaybookEngine | None" = None) -> None:
        """Initialise the scorer with an optional playbook engine.

        Args:
            playbook_engine: PlaybookEngine instance to call when the threat
                             threshold is crossed.  If None, scoring still runs
                             but no playbook is fired and incident is None.
        """
        self._playbook = playbook_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        lstm_score: float,
        siem_result: dict,
        event: dict,
    ) -> dict:
        """Compute the hybrid threat score and optionally fire the playbook.

        Args:
            lstm_score: Raw sigmoid output from the LSTM inference API [0.0–1.0].
            siem_result: Dict returned by ElasticSIEMCorrelator.evaluate().
                         Must contain 'siem_score' (float) and 'rules' (list).
            event: The original transaction event dict.  Passed through to the
                   PlaybookEngine so the incident record contains full evidence.

        Returns:
            Dict with keys:
                threat_score (float)    — blended value, rounded to 4 dp
                lstm_score (float)      — input LSTM score (passed through)
                siem_score (float)      — input SIEM score (passed through)
                verdict (str)           — "FLAGGED" or "MONITOR"
                trigger_reason (str)    — "HYBRID_THRESHOLD", "LSTM_ALONE", or "NONE"
                playbook_fired (bool)   — True if PlaybookEngine.fire() was called
                siem_rules (list)       — rule-level detail from siem_result
                incident (dict | None)  — incident payload if playbook fired
        """
        siem_score: float = float(siem_result.get("siem_score", 0.0))
        siem_rules: list = siem_result.get("rules", [])

        # Core blending formula from architecture spec
        threat_score = (_LSTM_WEIGHT * lstm_score) + (_SIEM_WEIGHT * siem_score)

        verdict, trigger_reason = self._determine_verdict(lstm_score, threat_score)

        result: dict = {
            "threat_score": round(threat_score, 4),
            "lstm_score": round(lstm_score, 4),
            "siem_score": round(siem_score, 4),
            "verdict": verdict,
            "trigger_reason": trigger_reason,
            "playbook_fired": False,
            "siem_rules": siem_rules,
            "incident": None,
            # Attach the event so callers can inspect it without separate storage
            "event": event,
        }

        if verdict == "FLAGGED" and self._playbook is not None:
            incident = self._playbook.fire(result)
            result["playbook_fired"] = True
            result["incident"] = incident
            logger.info(
                "Playbook fired | threat_score=%.4f | reason=%s | incident_id=%s",
                threat_score,
                trigger_reason,
                incident.get("incident_id"),
            )
        elif verdict == "MONITOR":
            logger.info(
                "Transaction in MONITOR state | threat_score=%.4f | lstm=%.4f | siem=%.4f",
                threat_score,
                lstm_score,
                siem_score,
            )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_verdict(lstm_score: float, threat_score: float) -> tuple[str, str]:
        """Apply the dual-threshold logic and return (verdict, trigger_reason).

        The hybrid threshold is checked first — it represents the strongest
        combined signal.  The LSTM_ALONE path catches high-confidence
        behavioural anomalies that the SIEM rules did not corroborate.
        """
        if threat_score >= _HYBRID_THRESHOLD:
            return "FLAGGED", "HYBRID_THRESHOLD"
        if lstm_score >= _LSTM_ALONE_THRESHOLD:
            return "FLAGGED", "LSTM_ALONE"
        return "MONITOR", "NONE"
