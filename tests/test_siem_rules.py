"""Unit tests for ElasticSIEMCorrelator — all four SIEM rules and score normalisation.

Each test is self-contained: the correlator is constructed with a tmp_path
watchlist so tests never depend on the state of the real watchlist/merchants.json.
"""

import json
from pathlib import Path

import pytest

from src.siem.rule_engine import ElasticSIEMCorrelator


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def watchlist_file(tmp_path: Path) -> Path:
    """Write a small watchlist JSON file and return its path."""
    path = tmp_path / "merchants.json"
    # M9921 is the known-bad merchant used in watchlist tests
    path.write_text(json.dumps(["M9921", "M4756", "M7891"]), encoding="utf-8")
    return path


@pytest.fixture()
def correlator(watchlist_file: Path) -> ElasticSIEMCorrelator:
    """Return a correlator backed by the test watchlist."""
    return ElasticSIEMCorrelator(watchlist_path=watchlist_file)


# ---------------------------------------------------------------------------
# Base events — a clean transaction that should not trigger any rule
# ---------------------------------------------------------------------------

def _clean_event() -> dict:
    """Minimal clean event: low amount, slow travel, business hours, safe merchant."""
    return {
        "amount": 500.0,
        # Sydney CBD → North Sydney (~3 km), 2 hours apart → ~1.5 km/h
        "lat": -33.8688, "lon": 151.2093,
        "prev_lat": -33.8397, "prev_lon": 151.2066,
        "timestamp":      "2025-06-30T10:00:00+10:00",
        "prev_timestamp": "2025-06-30T08:00:00+10:00",
        "merchant_id": "M0001",
    }


# ---------------------------------------------------------------------------
# Rule 1 — High-value amount
# ---------------------------------------------------------------------------

class TestRuleHighValue:
    def test_triggers_above_threshold(self, correlator: ElasticSIEMCorrelator) -> None:
        """Amount of $15,000 must trigger Rule 1 at HIGH severity."""
        event = _clean_event()
        event["amount"] = 15_000.0
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_001")

        assert rule["triggered"] is True
        assert rule["severity"] == "HIGH"
        assert rule["evidence"]["amount"] == 15_000.0

    def test_passes_below_threshold(self, correlator: ElasticSIEMCorrelator) -> None:
        """Amount of $5,000 must not trigger Rule 1."""
        event = _clean_event()
        event["amount"] = 5_000.0
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_001")

        assert rule["triggered"] is False

    def test_exact_threshold_does_not_trigger(self, correlator: ElasticSIEMCorrelator) -> None:
        """Amount exactly equal to $10,000 must not trigger (rule uses strict >)."""
        event = _clean_event()
        event["amount"] = 10_000.0
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_001")

        assert rule["triggered"] is False


# ---------------------------------------------------------------------------
# Rule 2 — Geo-velocity
# ---------------------------------------------------------------------------

class TestRuleGeoVelocity:
    def test_triggers_on_impossible_travel(self, correlator: ElasticSIEMCorrelator) -> None:
        """Sydney → Melbourne (~713 km) in 30 min → ~1,426 km/h triggers Rule 2."""
        event = _clean_event()
        # Sydney CBD
        event["lat"], event["lon"] = -33.8688, 151.2093
        # Melbourne CBD (~713 km away)
        event["prev_lat"], event["prev_lon"] = -37.8136, 144.9631
        event["timestamp"]      = "2025-06-30T10:30:00+10:00"
        event["prev_timestamp"] = "2025-06-30T10:00:00+10:00"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_002")

        assert rule["triggered"] is True
        assert rule["severity"] == "HIGH"
        # Evidence must contain a meaningful velocity reading
        assert rule["evidence"]["velocity_kmh"] > 500

    def test_passes_on_plausible_travel(self, correlator: ElasticSIEMCorrelator) -> None:
        """Sydney CBD → North Sydney (~3 km) in 2 hours is not impossible travel."""
        event = _clean_event()  # clean event already has these coordinates
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_002")

        assert rule["triggered"] is False

    def test_missing_geo_fields_does_not_trigger(self, correlator: ElasticSIEMCorrelator) -> None:
        """When location fields are absent the rule must not trigger and must record the gap."""
        event = {"amount": 500.0, "timestamp": "2025-06-30T10:00:00+10:00", "merchant_id": "M0001"}
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_002")

        assert rule["triggered"] is False
        assert "error" in rule["evidence"]

    def test_simultaneous_transactions_trigger(self, correlator: ElasticSIEMCorrelator) -> None:
        """Two transactions at distant locations with identical timestamps → infinite velocity."""
        event = _clean_event()
        event["lat"], event["lon"] = -33.8688, 151.2093          # Sydney
        event["prev_lat"], event["prev_lon"] = -37.8136, 144.9631  # Melbourne
        # Same timestamp → elapsed = 0 → infinite velocity
        event["timestamp"] = event["prev_timestamp"] = "2025-06-30T10:00:00+10:00"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_002")

        assert rule["triggered"] is True


# ---------------------------------------------------------------------------
# Rule 3 — Off-hours (AEST/AEDT)
# ---------------------------------------------------------------------------

class TestRuleOffHours:
    def test_triggers_late_night(self, correlator: ElasticSIEMCorrelator) -> None:
        """23:15 AEST is after 22:00 — must trigger Rule 3 at MEDIUM severity."""
        event = _clean_event()
        event["timestamp"] = "2025-06-30T23:15:00+10:00"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_003")

        assert rule["triggered"] is True
        assert rule["severity"] == "MEDIUM"
        assert rule["evidence"]["local_time"] == "23:15"

    def test_triggers_early_morning(self, correlator: ElasticSIEMCorrelator) -> None:
        """03:00 AEST is before 08:00 — must trigger Rule 3."""
        event = _clean_event()
        event["timestamp"] = "2025-06-30T03:00:00+10:00"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_003")

        assert rule["triggered"] is True

    def test_passes_business_hours(self, correlator: ElasticSIEMCorrelator) -> None:
        """10:00 AEST is within business hours — must not trigger Rule 3."""
        event = _clean_event()  # clean event uses 10:00 AEST
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_003")

        assert rule["triggered"] is False

    def test_boundary_22_00_triggers(self, correlator: ElasticSIEMCorrelator) -> None:
        """Exactly 22:00 AEST is the start of off-hours — must trigger."""
        event = _clean_event()
        event["timestamp"] = "2025-06-30T22:00:00+10:00"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_003")

        assert rule["triggered"] is True

    def test_boundary_07_59_triggers(self, correlator: ElasticSIEMCorrelator) -> None:
        """07:59 AEST is one minute before business hours — must trigger."""
        event = _clean_event()
        event["timestamp"] = "2025-06-30T07:59:00+10:00"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_003")

        assert rule["triggered"] is True

    def test_utc_timestamp_converted_correctly(self, correlator: ElasticSIEMCorrelator) -> None:
        """13:00 UTC = 23:00 AEST — must trigger off-hours rule."""
        event = _clean_event()
        event["timestamp"] = "2025-06-30T13:00:00+00:00"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_003")

        assert rule["triggered"] is True


# ---------------------------------------------------------------------------
# Rule 4 — Watchlist merchant
# ---------------------------------------------------------------------------

class TestRuleWatchlistMerchant:
    def test_triggers_on_watchlist_merchant(self, correlator: ElasticSIEMCorrelator) -> None:
        """M9921 is in the test watchlist — must trigger Rule 4 at HIGH severity."""
        event = _clean_event()
        event["merchant_id"] = "M9921"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_004")

        assert rule["triggered"] is True
        assert rule["severity"] == "HIGH"
        assert rule["evidence"]["merchant_id"] == "M9921"

    def test_passes_unknown_merchant(self, correlator: ElasticSIEMCorrelator) -> None:
        """M0001 is not in the watchlist — must not trigger Rule 4."""
        event = _clean_event()  # clean event uses M0001
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_004")

        assert rule["triggered"] is False

    def test_missing_merchant_id_does_not_trigger(self, correlator: ElasticSIEMCorrelator) -> None:
        """An event with no merchant_id must not trigger Rule 4."""
        event = _clean_event()
        del event["merchant_id"]
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_004")

        assert rule["triggered"] is False

    def test_empty_watchlist_never_triggers(self, tmp_path: Path) -> None:
        """A correlator with an empty watchlist must never fire Rule 4."""
        empty = tmp_path / "empty.json"
        empty.write_text("[]", encoding="utf-8")
        correlator = ElasticSIEMCorrelator(watchlist_path=empty)

        event = _clean_event()
        event["merchant_id"] = "M9921"
        result = correlator.evaluate(event)
        rule = next(r for r in result["rules"] if r["rule_id"] == "RULE_004")

        assert rule["triggered"] is False


# ---------------------------------------------------------------------------
# Score normalisation
# ---------------------------------------------------------------------------

class TestScoreNormalisation:
    def test_zero_rules_yields_zero(self, correlator: ElasticSIEMCorrelator) -> None:
        """Clean event → 0 triggered rules → siem_score = 0.00."""
        result = correlator.evaluate(_clean_event())
        assert result["triggered_count"] == 0
        assert result["siem_score"] == 0.00

    def test_one_rule_yields_0_33(self, correlator: ElasticSIEMCorrelator) -> None:
        """Exactly 1 triggered rule → siem_score = 0.33."""
        event = _clean_event()
        event["amount"] = 15_000.0  # only Rule 1 fires
        result = correlator.evaluate(event)
        assert result["triggered_count"] == 1
        assert result["siem_score"] == 0.33

    def test_two_rules_yields_0_67(self, correlator: ElasticSIEMCorrelator) -> None:
        """Exactly 2 triggered rules → siem_score = 0.67."""
        event = _clean_event()
        event["amount"] = 15_000.0          # Rule 1
        event["merchant_id"] = "M9921"      # Rule 4
        result = correlator.evaluate(event)
        assert result["triggered_count"] == 2
        assert result["siem_score"] == 0.67

    def test_three_or_more_rules_yields_1_00(self, correlator: ElasticSIEMCorrelator) -> None:
        """3 or more triggered rules → siem_score = 1.00."""
        event = _clean_event()
        event["amount"] = 15_000.0                  # Rule 1
        event["merchant_id"] = "M9921"              # Rule 4
        event["timestamp"] = "2025-06-30T23:15:00+10:00"  # Rule 3
        result = correlator.evaluate(event)
        assert result["triggered_count"] >= 3
        assert result["siem_score"] == 1.00


# ---------------------------------------------------------------------------
# All four rules fire simultaneously
# ---------------------------------------------------------------------------

class TestAllRulesFire:
    def test_all_four_rules_trigger(self, correlator: ElasticSIEMCorrelator) -> None:
        """Worst-case fraud event must trigger all four rules and return score 1.00."""
        event = {
            # Rule 1: high value
            "amount": 50_000.0,
            # Rule 2: Sydney → Melbourne in 30 min
            "lat": -33.8688, "lon": 151.2093,
            "prev_lat": -37.8136, "prev_lon": 144.9631,
            "timestamp":      "2025-06-30T23:30:00+10:00",
            "prev_timestamp": "2025-06-30T23:00:00+10:00",
            # Rule 3: 23:30 AEST is off-hours (timestamp above handles this)
            # Rule 4: watchlist merchant
            "merchant_id": "M9921",
        }
        result = correlator.evaluate(event)

        assert result["triggered_count"] == 4
        assert result["siem_score"] == 1.00

        triggered_ids = {r["rule_id"] for r in result["rules"] if r["triggered"]}
        assert triggered_ids == {"RULE_001", "RULE_002", "RULE_003", "RULE_004"}
