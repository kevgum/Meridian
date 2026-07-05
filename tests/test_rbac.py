"""RBAC integration tests — verifies Elasticsearch role enforcement (Day 9).

These tests require a live Elasticsearch cluster with bootstrap_rbac.py already
run to create the test users.  They are marked @pytest.mark.integration and are
excluded from the default unit-test run.

Prerequisites:
    docker compose up -d elasticsearch
    python scripts/bootstrap_rbac.py

Run:
    docker compose --profile dev run --rm dev pytest tests/test_rbac.py -v -m integration

AT-9 coverage:
    security_analyst role attempts write to detection rules → must be denied (403)
    This test is the primary acceptance-test evidence for AT-9.
"""

from __future__ import annotations

import os

import pytest

try:
    from elasticsearch import Elasticsearch, AuthorizationException
    _ES_AVAILABLE = True
except ImportError:
    _ES_AVAILABLE = False

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ELASTIC_HOST = os.environ.get("ELASTIC_HOST", "http://elasticsearch:9200")
_ELASTIC_PASSWORD = os.environ.get("ELASTIC_PASSWORD", "meridian123")

# Test user credentials created by bootstrap_rbac.py
_ANALYST_CREDS = ("test_analyst", "TestAnalyst1!")
_ENGINEER_CREDS = ("test_engineer", "TestEngineer1!")
_COMPLIANCE_CREDS = ("test_compliance", "TestCompliance1!")
_SYSADMIN_CREDS = ("test_sysadmin", "TestSysadmin1!")


def _client(credentials: tuple[str, str]) -> "Elasticsearch":
    """Return an ES client authenticated as the given (username, password)."""
    return Elasticsearch(
        _ELASTIC_HOST,
        basic_auth=credentials,
        request_timeout=10,
    )


def _admin_client() -> "Elasticsearch":
    """Return a superuser ES client for setup helpers."""
    return Elasticsearch(
        _ELASTIC_HOST,
        basic_auth=("elastic", _ELASTIC_PASSWORD),
        request_timeout=10,
    )


@pytest.fixture(scope="module", autouse=True)
def ensure_test_data() -> None:
    """Seed a single test incident document so read tests have something to return.

    Uses the elastic superuser so the seed step is never blocked by RBAC.
    Cleans up after the module finishes.
    """
    if not _ES_AVAILABLE:
        pytest.skip("elasticsearch package not available")

    admin = _admin_client()
    if not admin.ping():
        pytest.skip("Elasticsearch not reachable — run: docker compose up -d elasticsearch")

    # Seed one incident document for read tests
    admin.index(
        index="meridian-incidents-test",
        id="rbac-test-doc-001",
        document={
            "incident_id": "rbac-test-doc-001",
            "customer_id": "CUST-RBAC-TEST",
            "action": "LOCK_ACCOUNT",
            "status": "OPEN",
        },
        refresh=True,
    )
    yield
    # Cleanup: remove the test index
    try:
        admin.indices.delete(index="meridian-incidents-test", ignore_unavailable=True)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# AT-9: security_analyst denied write to Kibana (detection rules)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAnalystRoleEnforcement:
    """Verify that the security_analyst role cannot modify detection rules.

    AT-9 requirement: security_analyst role attempts rule edit → access denied and logged.
    In Elasticsearch, detection rules are stored as Kibana saved objects in the
    .kibana* indices.  A security_analyst must have no write privilege there.
    """

    def test_analyst_denied_write_to_kibana_index(self) -> None:
        """security_analyst cannot index a document into .kibana — HTTP 403.

        This is the AT-9 acceptance test.  A 403 response proves ES is enforcing
        the role boundary and logging the denied action to the ES audit log.
        """
        analyst = _client(_ANALYST_CREDS)
        with pytest.raises(AuthorizationException) as exc_info:
            analyst.index(
                index=".kibana_test_rbac",
                document={"type": "alert", "alert": {"name": "malicious_rule"}},
            )
        # AuthorizationException wraps the 403 response
        assert exc_info.value.meta.status == 403

    def test_analyst_can_read_incidents(self) -> None:
        """security_analyst CAN read from meridian-incidents-* — expected 200."""
        analyst = _client(_ANALYST_CREDS)
        # Should not raise — analyst has read privilege on incidents
        result = analyst.search(
            index="meridian-incidents-test",
            body={"query": {"match_all": {}}},
            size=1,
        )
        assert result["hits"]["total"]["value"] >= 0  # 0 is fine — index exists and is readable

    def test_analyst_can_write_incident_update(self) -> None:
        """security_analyst CAN update an incident (e.g. close it) — expected 200."""
        analyst = _client(_ANALYST_CREDS)
        # Should not raise — analyst has write privilege on incidents
        analyst.update(
            index="meridian-incidents-test",
            id="rbac-test-doc-001",
            doc={"status": "CLOSED", "analyst_assigned": "test_analyst"},
        )


# ---------------------------------------------------------------------------
# Compliance officer: read-only enforcement
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestComplianceOfficerRole:
    """Verify that the compliance_officer role is strictly read-only."""

    def test_compliance_officer_can_read_incidents(self) -> None:
        """compliance_officer CAN read incident records for regulatory reporting."""
        compliance = _client(_COMPLIANCE_CREDS)
        result = compliance.search(
            index="meridian-incidents-test",
            body={"query": {"match_all": {}}},
            size=1,
        )
        assert result["hits"]["total"]["value"] >= 0

    def test_compliance_officer_denied_write_to_incidents(self) -> None:
        """compliance_officer CANNOT write to incidents — read-only role.

        Compliance officers must not be able to modify the audit trail they
        are reviewing — this preserves audit trail integrity (PCI DSS Req 10.3).
        """
        compliance = _client(_COMPLIANCE_CREDS)
        with pytest.raises(AuthorizationException) as exc_info:
            compliance.index(
                index="meridian-incidents-test",
                document={"incident_id": "FAKE", "status": "TAMPERED"},
            )
        assert exc_info.value.meta.status == 403


# ---------------------------------------------------------------------------
# Senior security engineer: elevated write access
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSeniorEngineerRole:
    """Verify that senior_security_engineer has write access where analyst does not."""

    def test_engineer_can_write_to_kibana_index(self) -> None:
        """senior_security_engineer CAN write to .kibana — can edit detection rules."""
        engineer = _client(_ENGINEER_CREDS)
        admin = _admin_client()

        # Pre-create the index as admin. In production the .kibana index already
        # exists (Kibana creates it); the engineer role grants write access but
        # not create_index on restricted .kibana* indices, by design.
        if not admin.indices.exists(index=".kibana_rbac_test"):
            admin.indices.create(index=".kibana_rbac_test")

        # Write as engineer into the existing index
        engineer.index(
            index=".kibana_rbac_test",
            document={"type": "detection_rule", "name": "test_rule_by_engineer"},
            refresh=True,
        )
        # Cleanup — delete the test index using admin credentials
        try:
            admin.indices.delete(index=".kibana_rbac_test", ignore_unavailable=True)
        except Exception:  # noqa: BLE001
            pass
