"""Unit tests for HybridThreatScorer and PlaybookEngine (Day 8).

All tests are pure unit tests — no running Docker services are required.
The Elasticsearch client and PlaybookEngine are substituted with MagicMocks
so the test suite runs identically locally and inside the dev container.

Run:
    docker compose --profile dev run --rm dev pytest tests/test_hybrid_scorer.py -v

E2E tests that exercise the live LSTM API and Elasticsearch cluster are
marked with @pytest.mark.e2e and excluded from the default run.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src.siem.hybrid_scorer import HybridThreatScorer
from src.siem.playbook_engine import PlaybookEngine, _severity_from_score


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_siem_result(
    siem_score: float = 0.00,
    triggered_count: int = 0,
    rules: list | None = None,
) -> dict:
    """Build a minimal siem_result dict matching ElasticSIEMCorrelator output."""
    return {
        "siem_score": siem_score,
        "triggered_count": triggered_count,
        "rules": rules or [],
    }


def _make_event(amount: float = 500.0, merchant_id: str = "M0001") -> dict:
    """Build a minimal transaction event dict."""
    return {
        "amount": amount,
        "merchant_id": merchant_id,
        "timestamp": "2026-06-30T10:00:00Z",
        "lat": -33.8688,
        "lon": 151.2093,
        "customer_id": "CUST-TEST-001",
    }


# ---------------------------------------------------------------------------
# HybridThreatScorer — formula correctness
# ---------------------------------------------------------------------------

class TestHybridFormula:
    """Verify the blending formula: (lstm × 0.60) + (siem × 0.40)."""

    def test_formula_correct_mixed_scores(self) -> None:
        """lstm=0.50, siem=0.33 → threat_score = 0.432."""
        scorer = HybridThreatScorer()
        result = scorer.score(
            lstm_score=0.50,
            siem_result=_make_siem_result(siem_score=0.33),
            event=_make_event(),
        )
        # (0.50 × 0.60) + (0.33 × 0.40) = 0.300 + 0.132 = 0.432
        assert result["threat_score"] == pytest.approx(0.432, abs=1e-4)

    def test_formula_all_zeros(self) -> None:
        """Zero scores produce zero threat_score."""
        scorer = HybridThreatScorer()
        result = scorer.score(0.0, _make_siem_result(0.0), _make_event())
        assert result["threat_score"] == 0.0

    def test_formula_all_ones(self) -> None:
        """Maximum scores produce threat_score = 1.00."""
        scorer = HybridThreatScorer()
        result = scorer.score(1.0, _make_siem_result(1.0), _make_event())
        assert result["threat_score"] == pytest.approx(1.0, abs=1e-4)

    def test_result_contains_input_scores(self) -> None:
        """Score dict echoes lstm_score and siem_score for downstream logging."""
        scorer = HybridThreatScorer()
        result = scorer.score(0.55, _make_siem_result(0.67), _make_event())
        assert result["lstm_score"] == pytest.approx(0.55, abs=1e-4)
        assert result["siem_score"] == pytest.approx(0.67, abs=1e-4)


# ---------------------------------------------------------------------------
# HybridThreatScorer — verdict and trigger logic
# ---------------------------------------------------------------------------

class TestVerdictLogic:
    """Verify FLAGGED / MONITOR verdicts and trigger_reason values."""

    def test_hybrid_threshold_fires_playbook(self) -> None:
        """Combined score >= 0.70 → FLAGGED with reason HYBRID_THRESHOLD."""
        # lstm=0.60, siem=1.00 → (0.60×0.6)+(1.00×0.4) = 0.36+0.40 = 0.76
        scorer = HybridThreatScorer()
        result = scorer.score(0.60, _make_siem_result(1.00), _make_event())
        assert result["verdict"] == "FLAGGED"
        assert result["trigger_reason"] == "HYBRID_THRESHOLD"

    def test_lstm_alone_fires_playbook(self) -> None:
        """lstm >= 0.70 with siem = 0.00 → FLAGGED with reason LSTM_ALONE.

        This covers the CUST-18656 scenario: all 4 SIEM rules pass,
        but the LSTM returns 0.74 — hybrid would only be 0.444 without this path.
        """
        scorer = HybridThreatScorer()
        result = scorer.score(0.74, _make_siem_result(0.00), _make_event())
        assert result["verdict"] == "FLAGGED"
        assert result["trigger_reason"] == "LSTM_ALONE"
        # Confirm the hybrid formula alone would NOT have triggered
        assert result["threat_score"] == pytest.approx(0.444, abs=1e-4)

    def test_below_both_thresholds_is_monitor(self) -> None:
        """lstm < 0.70 and hybrid < 0.70 → MONITOR."""
        scorer = HybridThreatScorer()
        result = scorer.score(0.50, _make_siem_result(0.33), _make_event())
        assert result["verdict"] == "MONITOR"
        assert result["trigger_reason"] == "NONE"

    def test_boundary_exactly_0_70_hybrid_triggers(self) -> None:
        """threat_score == 0.70 exactly crosses the >= boundary."""
        # Need: (lstm × 0.6) + (siem × 0.4) == 0.70
        # Use lstm=0.50, siem=1.00 → (0.30 + 0.40) = 0.70
        scorer = HybridThreatScorer()
        result = scorer.score(0.50, _make_siem_result(1.00), _make_event())
        assert result["threat_score"] == pytest.approx(0.70, abs=1e-4)
        assert result["verdict"] == "FLAGGED"
        assert result["trigger_reason"] == "HYBRID_THRESHOLD"

    def test_boundary_just_below_0_70_is_monitor(self) -> None:
        """threat_score just below 0.70 stays MONITOR (not >= threshold)."""
        # lstm=0.50, siem=0.99 → (0.30 + 0.396) = 0.696
        scorer = HybridThreatScorer()
        result = scorer.score(0.50, _make_siem_result(0.99), _make_event())
        assert result["threat_score"] < 0.70
        assert result["verdict"] == "MONITOR"

    def test_lstm_boundary_exactly_0_70_alone_triggers(self) -> None:
        """lstm_score == 0.70 exactly triggers LSTM_ALONE when hybrid < 0.70."""
        # siem=0.00 so hybrid = 0.70×0.60 = 0.42 (< 0.70), LSTM_ALONE fires
        scorer = HybridThreatScorer()
        result = scorer.score(0.70, _make_siem_result(0.00), _make_event())
        assert result["verdict"] == "FLAGGED"
        assert result["trigger_reason"] == "LSTM_ALONE"

    def test_hybrid_threshold_checked_before_lstm_alone(self) -> None:
        """When hybrid >= 0.70 AND lstm >= 0.70, reason is HYBRID_THRESHOLD (not LSTM_ALONE)."""
        # lstm=0.80, siem=1.00 → hybrid = 0.48+0.40 = 0.88 >= 0.70 → HYBRID_THRESHOLD wins
        scorer = HybridThreatScorer()
        result = scorer.score(0.80, _make_siem_result(1.00), _make_event())
        assert result["trigger_reason"] == "HYBRID_THRESHOLD"


# ---------------------------------------------------------------------------
# HybridThreatScorer — PlaybookEngine integration
# ---------------------------------------------------------------------------

class TestPlaybookIntegration:
    """Verify the scorer calls (or skips) the playbook engine correctly."""

    def test_playbook_called_when_flagged(self) -> None:
        """PlaybookEngine.fire() is called exactly once when verdict is FLAGGED."""
        mock_engine = MagicMock()
        mock_engine.fire.return_value = {"incident_id": "test-123"}
        scorer = HybridThreatScorer(playbook_engine=mock_engine)

        scorer.score(0.74, _make_siem_result(0.00), _make_event())

        mock_engine.fire.assert_called_once()

    def test_playbook_not_called_when_monitor(self) -> None:
        """PlaybookEngine.fire() is NOT called when verdict is MONITOR."""
        mock_engine = MagicMock()
        scorer = HybridThreatScorer(playbook_engine=mock_engine)

        scorer.score(0.30, _make_siem_result(0.00), _make_event())

        mock_engine.fire.assert_not_called()

    def test_no_playbook_engine_does_not_crash(self) -> None:
        """Scorer with no engine completes without error; playbook_fired is False."""
        scorer = HybridThreatScorer(playbook_engine=None)
        result = scorer.score(0.80, _make_siem_result(1.00), _make_event())
        assert result["playbook_fired"] is False
        assert result["incident"] is None

    def test_incident_dict_attached_to_result(self) -> None:
        """The incident dict returned by the playbook appears in result['incident']."""
        fake_incident = {"incident_id": "abc-def", "action": "LOCK_ACCOUNT"}
        mock_engine = MagicMock()
        mock_engine.fire.return_value = fake_incident
        scorer = HybridThreatScorer(playbook_engine=mock_engine)

        result = scorer.score(0.74, _make_siem_result(0.00), _make_event())

        assert result["incident"] == fake_incident
        assert result["playbook_fired"] is True

    def test_playbook_receives_full_scorer_result(self) -> None:
        """PlaybookEngine.fire() receives the scorer result dict (not just the event)."""
        mock_engine = MagicMock()
        mock_engine.fire.return_value = {"incident_id": "xyz"}
        scorer = HybridThreatScorer(playbook_engine=mock_engine)

        event = _make_event(amount=15000.0)
        scorer.score(0.74, _make_siem_result(0.00), event)

        # The dict passed to fire() must include threat_score and event keys
        fired_arg = mock_engine.fire.call_args[0][0]
        assert "threat_score" in fired_arg
        assert "event" in fired_arg
        assert fired_arg["event"]["amount"] == 15000.0

    def test_siem_rules_passed_through(self) -> None:
        """siem_rules list from siem_result appears in the score output."""
        rules = [{"rule_id": "RULE_001", "triggered": True, "severity": "HIGH", "evidence": {}}]
        scorer = HybridThreatScorer()
        result = scorer.score(0.30, _make_siem_result(0.33, rules=rules), _make_event())
        assert result["siem_rules"] == rules


# ---------------------------------------------------------------------------
# PlaybookEngine — incident construction
# ---------------------------------------------------------------------------

class TestPlaybookEngine:
    """Unit tests for PlaybookEngine — all using a MagicMock ES client."""

    def _engine_with_mock_es(self) -> tuple[PlaybookEngine, MagicMock]:
        """Return an engine with a mock ES client and the mock for assertions."""
        mock_es = MagicMock()
        engine = PlaybookEngine(es_client=mock_es)
        return engine, mock_es

    def _minimal_scorer_result(self, threat_score: float = 0.74) -> dict:
        """Minimal scorer_result dict expected by PlaybookEngine.fire()."""
        return {
            "threat_score": threat_score,
            "lstm_score": 0.74,
            "siem_score": 0.00,
            "trigger_reason": "LSTM_ALONE",
            "siem_rules": [],
            "event": _make_event(),
        }

    def test_fire_returns_incident_dict(self) -> None:
        """fire() returns a dict with all required incident fields."""
        engine, _ = self._engine_with_mock_es()
        incident = engine.fire(self._minimal_scorer_result())
        required_keys = {
            "incident_id", "customer_id", "action", "timestamp",
            "threat_score", "lstm_score", "siem_score", "trigger_reason",
            "severity", "siem_rules", "evidence", "status", "analyst_assigned",
        }
        assert required_keys.issubset(incident.keys())

    def test_fire_generates_unique_uuid(self) -> None:
        """Each call to fire() produces a distinct UUID4 incident_id."""
        engine, _ = self._engine_with_mock_es()
        id1 = engine.fire(self._minimal_scorer_result())["incident_id"]
        id2 = engine.fire(self._minimal_scorer_result())["incident_id"]
        # Validate UUID4 format
        uuid.UUID(id1, version=4)
        uuid.UUID(id2, version=4)
        assert id1 != id2

    def test_fire_sets_lock_account_action(self) -> None:
        """Playbook always issues LOCK_ACCOUNT as the containment action."""
        engine, _ = self._engine_with_mock_es()
        incident = engine.fire(self._minimal_scorer_result())
        assert incident["action"] == "LOCK_ACCOUNT"

    def test_fire_sets_status_open(self) -> None:
        """New incidents start in OPEN status awaiting analyst triage."""
        engine, _ = self._engine_with_mock_es()
        incident = engine.fire(self._minimal_scorer_result())
        assert incident["status"] == "OPEN"
        assert incident["analyst_assigned"] is None

    def test_fire_writes_to_elasticsearch(self) -> None:
        """fire() writes the incident document to a meridian-incidents index."""
        engine, mock_es = self._engine_with_mock_es()
        incident = engine.fire(self._minimal_scorer_result())
        # fire() writes both an incident and a notification document
        assert mock_es.index.call_count == 2
        incident_calls = [
            c for c in mock_es.index.call_args_list
            if "meridian-incidents-" in c.kwargs["index"]
        ]
        assert len(incident_calls) == 1
        assert incident_calls[0].kwargs["document"]["incident_id"] == incident["incident_id"]

    def test_fire_elasticsearch_failure_does_not_raise(self) -> None:
        """An ES write failure logs an error but does NOT propagate — notification must still fire."""
        mock_es = MagicMock()
        mock_es.index.side_effect = ConnectionError("ES unreachable")
        engine = PlaybookEngine(es_client=mock_es)
        # Should not raise even though ES is down
        incident = engine.fire(self._minimal_scorer_result())
        assert incident["incident_id"]  # incident dict is still returned

    def test_severity_critical_above_0_90(self) -> None:
        """threat_score >= 0.90 maps to CRITICAL severity."""
        assert _severity_from_score(0.95, "HYBRID_THRESHOLD") == "CRITICAL"
        assert _severity_from_score(0.90, "HYBRID_THRESHOLD") == "CRITICAL"

    def test_severity_high_below_0_90(self) -> None:
        """threat_score in [0.70, 0.90) maps to HIGH severity."""
        assert _severity_from_score(0.74, "LSTM_ALONE") == "HIGH"
        assert _severity_from_score(0.70, "HYBRID_THRESHOLD") == "HIGH"
        assert _severity_from_score(0.89, "HYBRID_THRESHOLD") == "HIGH"

    def test_customer_id_extracted_from_event(self) -> None:
        """customer_id is pulled from event.customer_id when ECS field absent."""
        engine, _ = self._engine_with_mock_es()
        result = self._minimal_scorer_result()
        result["event"]["customer_id"] = "CUST-18656"
        incident = engine.fire(result)
        assert incident["customer_id"] == "CUST-18656"

    def test_customer_id_from_ecs_source_user(self) -> None:
        """customer_id is pulled from ECS source.user.id if present (post-Logstash events)."""
        engine, _ = self._engine_with_mock_es()
        result = self._minimal_scorer_result()
        result["event"]["source"] = {"user": {"id": "sha256-abc123"}}
        incident = engine.fire(result)
        assert incident["customer_id"] == "sha256-abc123"


# ---------------------------------------------------------------------------
# CUST-18656 scenario — end-to-end unit simulation
# ---------------------------------------------------------------------------

class TestCUST18656Scenario:
    """Simulate the CUST-18656 validation scenario without live services.

    CUST-18656: Darwin NT, 6 purchases at electronics/restaurant merchants.
    All 4 SIEM rules pass.  LSTM returns ~0.74.
    Expected: LSTM_ALONE trigger, playbook fires, severity=HIGH.
    """

    def test_cust18656_lstm_alone_triggers(self) -> None:
        """CUST-18656: siem_score=0.00, lstm=0.74 → LSTM_ALONE trigger."""
        mock_engine = MagicMock()
        mock_engine.fire.return_value = {
            "incident_id": "cust18656-test",
            "action": "LOCK_ACCOUNT",
            "severity": "HIGH",
        }
        scorer = HybridThreatScorer(playbook_engine=mock_engine)

        # All 4 SIEM rules pass for this legitimate-looking domestic transaction
        siem_result = _make_siem_result(siem_score=0.00, triggered_count=0)
        event = {
            "customer_id": "CUST-18656",
            "amount": 256.74,
            "merchant_id": "M5732",  # MCC 5732 electronics
            "timestamp": "2026-06-30T14:30:00+09:30",  # Darwin ACST — within business hours
            "lat": -12.4634,  # Darwin, NT
            "lon": 130.8456,
        }

        result = scorer.score(lstm_score=0.74, siem_result=siem_result, event=event)

        assert result["verdict"] == "FLAGGED"
        assert result["trigger_reason"] == "LSTM_ALONE"
        assert result["playbook_fired"] is True
        # Confirm hybrid score alone would NOT have triggered (< 0.70)
        assert result["threat_score"] == pytest.approx(0.444, abs=1e-4)

    def test_cust18656_incident_severity_is_high(self) -> None:
        """CUST-18656 incident severity is HIGH (threat_score 0.444 < 0.90)."""
        engine, mock_es = MagicMock(), MagicMock()
        engine = PlaybookEngine(es_client=mock_es)
        scorer_result = {
            "threat_score": 0.444,
            "lstm_score": 0.74,
            "siem_score": 0.00,
            "trigger_reason": "LSTM_ALONE",
            "siem_rules": [],
            "event": {"customer_id": "CUST-18656", "amount": 256.74},
        }
        incident = engine.fire(scorer_result)
        assert incident["severity"] == "HIGH"
