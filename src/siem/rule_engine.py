"""SIEM rule engine — evaluates four detection rules and returns a normalised threat score.

Each rule returns a result dict: {rule_id, triggered, severity, evidence}.
The correlator is stateless with respect to Elasticsearch; it operates purely on
the event dict passed to evaluate().  Live ES queries are wired in Day 8 when
the hybrid scorer orchestrates the full pipeline.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# AEST/AEDT — correctly handles daylight saving.
# On Windows, ZoneInfo requires the `tzdata` package (pip install tzdata).
# On Linux/Mac the system IANA database is used automatically.
try:
    _AEST = ZoneInfo("Australia/Sydney")
except ZoneInfoNotFoundError:
    # Fallback: UTC+10 fixed offset (no daylight saving).
    # Install tzdata to get correct AEDT handling.
    from datetime import timedelta, timezone as _tz
    _AEST = _tz(timedelta(hours=10))  # type: ignore[assignment]

# Earth radius used for Haversine distance calculation
_EARTH_RADIUS_KM = 6_371.0

# Normalised SIEM score lookup: number of triggered rules → score
# 3 or more rules map to 1.00 via the .get() fallback in evaluate()
_SCORE_MAP: dict[int, float] = {0: 0.00, 1: 0.33, 2: 0.67}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two coordinate pairs.

    Uses the Haversine formula, which is accurate to within ~0.3% for distances
    relevant to fraud detection (a few km to thousands of km).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class ElasticSIEMCorrelator:
    """Evaluates four SIEM detection rules against a normalised transaction event.

    Usage::

        correlator = ElasticSIEMCorrelator()
        result = correlator.evaluate(event)
        # result["siem_score"] → float in {0.00, 0.33, 0.67, 1.00}
        # result["rules"]     → list of per-rule dicts
    """

    # Rule thresholds — defined as class attributes so tests can override them
    HIGH_VALUE_THRESHOLD_AUD: float = 10_000.0
    GEO_VELOCITY_THRESHOLD_KMH: float = 500.0
    # Business hours window in local (AEST/AEDT) time
    BUSINESS_HOURS_START: int = 8   # 08:00 inclusive
    BUSINESS_HOURS_END: int = 22    # 22:00 — transactions at/after this are off-hours

    def __init__(self, watchlist_path: str | Path = "watchlist/merchants.json") -> None:
        """Initialise the correlator and load the merchant watchlist.

        Args:
            watchlist_path: Path to a JSON file containing known-bad merchant IDs.
                            Accepts a list of strings or a dict with a "merchants" key.
                            If the file does not exist, the watchlist is empty (Rule 4 never fires).
        """
        self._watchlist: set[str] = self._load_watchlist(Path(watchlist_path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, event: dict) -> dict:
        """Evaluate all four SIEM rules against a transaction event dict.

        Required keys vary per rule — see individual rule methods for details.
        Missing keys cause the affected rule to return triggered=False with an
        error note in evidence rather than raising an exception.

        Args:
            event: Normalised transaction dict produced by the feature pipeline
                   or Logstash, containing raw transaction fields alongside the
                   12 engineered LSTM features.

        Returns:
            Dict containing:
                rules (list[dict]): One result per rule with keys
                    rule_id, triggered, severity, evidence.
                siem_score (float): Normalised score — 0.00, 0.33, 0.67, or 1.00.
                triggered_count (int): How many rules fired (0–4).
        """
        results = [
            self._rule_high_value(event),
            self._rule_geo_velocity(event),
            self._rule_off_hours(event),
            self._rule_watchlist_merchant(event),
        ]

        triggered_count = sum(1 for r in results if r["triggered"])
        # 3+ rules always yields 1.00; _SCORE_MAP handles 0–2
        siem_score = _SCORE_MAP.get(triggered_count, 1.00)

        return {
            "rules": results,
            "siem_score": round(siem_score, 2),
            "triggered_count": triggered_count,
        }

    # ------------------------------------------------------------------
    # Rule implementations
    # ------------------------------------------------------------------

    def _rule_high_value(self, event: dict) -> dict:
        """Rule 1 — transaction amount exceeds AUD 10,000.

        Severity: HIGH
        Required event key: amount (numeric)
        """
        amount = float(event.get("amount", 0.0))
        triggered = amount > self.HIGH_VALUE_THRESHOLD_AUD

        return {
            "rule_id": "RULE_001",
            "triggered": triggered,
            "severity": "HIGH",
            "evidence": {
                "amount": amount,
                "threshold": self.HIGH_VALUE_THRESHOLD_AUD,
            },
        }

    def _rule_geo_velocity(self, event: dict) -> dict:
        """Rule 2 — travel speed between consecutive transactions exceeds 500 km/h.

        Computed via Haversine distance / elapsed time.  This threshold flags
        physically impossible travel and indicates a stolen card used in two
        locations near-simultaneously.

        Severity: HIGH
        Required event keys: lat, lon, timestamp, prev_lat, prev_lon, prev_timestamp
        """
        required_keys = ("lat", "lon", "timestamp", "prev_lat", "prev_lon", "prev_timestamp")
        missing = [k for k in required_keys if k not in event]
        if missing:
            # Cannot evaluate without location history — do not trigger
            return {
                "rule_id": "RULE_002",
                "triggered": False,
                "severity": "HIGH",
                "evidence": {"error": f"missing fields: {missing}"},
            }

        distance_km = _haversine_km(
            float(event["prev_lat"]), float(event["prev_lon"]),
            float(event["lat"]),      float(event["lon"]),
        )

        t_curr = self._parse_timestamp(event["timestamp"])
        t_prev = self._parse_timestamp(event["prev_timestamp"])
        elapsed_hours = (t_curr - t_prev).total_seconds() / 3_600.0

        # Simultaneous transactions (elapsed == 0) yield infinite velocity — always trigger
        velocity_kmh = (distance_km / elapsed_hours) if elapsed_hours > 0 else float("inf")
        triggered = velocity_kmh > self.GEO_VELOCITY_THRESHOLD_KMH

        return {
            "rule_id": "RULE_002",
            "triggered": triggered,
            "severity": "HIGH",
            "evidence": {
                "velocity_kmh": round(velocity_kmh, 1),
                "distance_km": round(distance_km, 1),
                "elapsed_hours": round(elapsed_hours, 4),
                "threshold_kmh": self.GEO_VELOCITY_THRESHOLD_KMH,
            },
        }

    def _rule_off_hours(self, event: dict) -> dict:
        """Rule 3 — transaction occurred outside business hours in Australian Eastern Time.

        Business hours are 08:00–21:59 AEST/AEDT.  Transactions before 08:00 or
        at/after 22:00 local time are flagged.  ZoneInfo("Australia/Sydney") is used
        so daylight saving transitions are handled automatically.

        Severity: MEDIUM
        Required event key: timestamp (ISO 8601 string or datetime object)
        """
        if "timestamp" not in event:
            return {
                "rule_id": "RULE_003",
                "triggered": False,
                "severity": "MEDIUM",
                "evidence": {"error": "missing field: timestamp"},
            }

        local_ts = self._parse_timestamp(event["timestamp"]).astimezone(_AEST)
        hour = local_ts.hour
        triggered = hour < self.BUSINESS_HOURS_START or hour >= self.BUSINESS_HOURS_END

        return {
            "rule_id": "RULE_003",
            "triggered": triggered,
            "severity": "MEDIUM",
            "evidence": {
                "local_time": local_ts.strftime("%H:%M"),
                "timezone": "Australia/Sydney",
                "off_hours_window": (
                    f"before {self.BUSINESS_HOURS_START:02d}:00 "
                    f"or at/after {self.BUSINESS_HOURS_END:02d}:00"
                ),
            },
        }

    def _rule_watchlist_merchant(self, event: dict) -> dict:
        """Rule 4 — merchant ID appears in the known-bad watchlist.

        The watchlist is loaded from disk once at __init__ time and held in a
        set for O(1) lookup.  Populated from watchlist/merchants.json.

        Severity: HIGH
        Required event key: merchant_id (string)
        """
        merchant_id = str(event.get("merchant_id", ""))
        triggered = bool(merchant_id) and merchant_id in self._watchlist

        return {
            "rule_id": "RULE_004",
            "triggered": triggered,
            "severity": "HIGH",
            "evidence": {
                "merchant_id": merchant_id,
                "watchlist_size": len(self._watchlist),
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_watchlist(path: Path) -> set[str]:
        """Load merchant IDs from a JSON file into a set.

        Accepts two JSON shapes:
            - A top-level list: ["M1042", "M2234", ...]
            - A dict with a "merchants" key: {"merchants": ["M1042", ...]}
        """
        if not path.exists():
            return set()
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return set(str(item) for item in data)
        return set(str(item) for item in data.get("merchants", []))

    @staticmethod
    def _parse_timestamp(value: str | datetime) -> datetime:
        """Parse an ISO 8601 string into a timezone-aware datetime.

        Naive datetimes (no tzinfo) are assumed to be UTC, matching the
        expectation that Logstash emits UTC timestamps.
        """
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value))
        # Attach UTC if naive so astimezone() conversions work correctly
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
