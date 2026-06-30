"""Bootstrap RBAC — creates the 6 Meridian Sentinel roles and test users in Elasticsearch.

Run once after the stack is up:
    python scripts/bootstrap_rbac.py

Idempotent — safe to re-run.  Existing roles and users are updated in place.

The script also generates an API key for the feature-engineering service so it
can authenticate without embedding the elastic superuser password in source code.
The API key is printed to stdout and must be copied into .env as ELASTIC_API_KEY.

Environment variables (read from .env or shell):
    ELASTIC_HOST      — default http://localhost:9200
    ELASTIC_PASSWORD  — default meridian123 (elastic superuser)
"""

from __future__ import annotations

import os
import sys
from typing import Any

from elasticsearch import Elasticsearch, BadRequestError

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_HOST = os.environ.get("ELASTIC_HOST", "http://localhost:9200")
_PASSWORD = os.environ.get("ELASTIC_PASSWORD", "meridian123")


def _connect() -> Elasticsearch:
    """Return an authenticated ES client using the elastic superuser."""
    return Elasticsearch(_HOST, basic_auth=("elastic", _PASSWORD), request_timeout=30)


# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------

# Each entry: (role_name, cluster_privileges, index_rules)
# index_rules: list of {names, privileges} dicts

_ROLES: list[dict[str, Any]] = [
    {
        "name": "security_analyst",
        "description": "Read transactions and incidents; create/update/close incident records.",
        "cluster": [],
        "indices": [
            # Read access to transaction feed for alert investigation
            {
                "names": ["meridian-transactions-*"],
                "privileges": ["read", "view_index_metadata"],
            },
            # Full write access to incidents — analysts triage and close these
            {
                "names": ["meridian-incidents-*"],
                "privileges": ["read", "write", "create", "index", "view_index_metadata"],
            },
            # Read-only audit trail — analysts can view but not modify
            {
                "names": ["meridian-audit-*"],
                "privileges": ["read", "view_index_metadata"],
            },
        ],
    },
    {
        "name": "senior_security_engineer",
        "description": "All analyst permissions plus write access to detection rules and playbook config.",
        "cluster": ["monitor"],
        "indices": [
            {
                "names": ["meridian-*"],
                "privileges": ["read", "write", "create", "index", "delete", "view_index_metadata"],
            },
            # Kibana saved objects — needed to edit detection rules in the UI
            {
                "names": [".kibana*"],
                "privileges": ["read", "write", "create", "index", "view_index_metadata"],
            },
        ],
    },
    {
        "name": "ml_operations",
        "description": "Read all meridian indices; write model artifact and retraining indices.",
        "cluster": [],
        "indices": [
            {"names": ["meridian-*"], "privileges": ["read", "view_index_metadata"]},
            {
                "names": ["meridian-model-*"],
                "privileges": ["read", "write", "create", "index", "view_index_metadata"],
            },
        ],
    },
    {
        "name": "compliance_officer",
        "description": "Read-only access to audit logs and incident records for regulatory reporting.",
        "cluster": [],
        "indices": [
            {
                "names": ["meridian-audit-*", "meridian-incidents-*"],
                "privileges": ["read", "view_index_metadata"],
            },
        ],
    },
    {
        "name": "system_administrator",
        "description": "Full administrative access to all indices and cluster management.",
        "cluster": ["all"],
        "indices": [
            {"names": ["*"], "privileges": ["all"]},
        ],
    },
    {
        "name": "read_only_auditor",
        "description": "External auditor — read-only access to the audit trail only.",
        "cluster": [],
        "indices": [
            {
                "names": ["meridian-audit-*"],
                "privileges": ["read", "view_index_metadata"],
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Test user definitions
# Passwords meet ES complexity requirements (upper, lower, digit, symbol).
# These are prototype-only credentials — never use in production.
# ---------------------------------------------------------------------------

_TEST_USERS: list[dict[str, str]] = [
    {
        "username": "test_analyst",
        "password": "TestAnalyst1!",
        "roles": "security_analyst",
        "full_name": "Test Security Analyst",
        "email": "analyst@meridian-test.local",
    },
    {
        "username": "test_engineer",
        "password": "TestEngineer1!",
        "roles": "senior_security_engineer",
        "full_name": "Test Senior Security Engineer",
        "email": "engineer@meridian-test.local",
    },
    {
        "username": "test_ml_ops",
        "password": "TestMlOps1!",
        "roles": "ml_operations",
        "full_name": "Test ML Operations",
        "email": "mlops@meridian-test.local",
    },
    {
        "username": "test_compliance",
        "password": "TestCompliance1!",
        "roles": "compliance_officer",
        "full_name": "Test Compliance Officer",
        "email": "compliance@meridian-test.local",
    },
    {
        "username": "test_sysadmin",
        "password": "TestSysadmin1!",
        "roles": "system_administrator",
        "full_name": "Test System Administrator",
        "email": "sysadmin@meridian-test.local",
    },
    {
        "username": "test_auditor",
        "password": "TestAuditor1!",
        "roles": "read_only_auditor",
        "full_name": "Test External Auditor",
        "email": "auditor@meridian-test.local",
    },
]


# ---------------------------------------------------------------------------
# Bootstrap functions
# ---------------------------------------------------------------------------

def create_roles(es: Elasticsearch) -> None:
    """Create or update all 6 Meridian Sentinel roles."""
    print("\n── Creating roles ──────────────────────────────────────────")
    for role in _ROLES:
        name = role["name"]
        es.security.put_role(
            name=name,
            cluster=role["cluster"],
            indices=role["indices"],
        )
        print(f"  ✅ {name}")


def create_users(es: Elasticsearch) -> None:
    """Create or update the 6 prototype test users."""
    print("\n── Creating test users ─────────────────────────────────────")
    for user in _TEST_USERS:
        es.security.put_user(
            username=user["username"],
            password=user["password"],
            roles=[user["roles"]],
            full_name=user["full_name"],
            email=user["email"],
            enabled=True,
        )
        print(f"  ✅ {user['username']} → role: {user['roles']}")


def create_api_key(es: Elasticsearch) -> str:
    """Create an API key for the feature-engineering service.

    The key is scoped to the indices the service actually needs:
    meridian-transactions-* (read) and meridian-incidents-* (read).
    Using a scoped key means a compromised key cannot affect other indices.

    Returns:
        The encoded API key string to store in .env as ELASTIC_API_KEY.
    """
    print("\n── Creating feature-engineering API key ────────────────────")
    try:
        response = es.security.create_api_key(
            name="feature-engineering-service",
            role_descriptors={
                "feature_engineering": {
                    "cluster": [],
                    "indices": [
                        {
                            "names": ["meridian-transactions-*", "meridian-incidents-*"],
                            "privileges": ["read", "view_index_metadata"],
                        }
                    ],
                }
            },
        )
        # encoded is the value to use in Authorization: ApiKey <encoded>
        encoded = response["encoded"]
        print(f"  ✅ API key created: {response['name']} (id: {response['id']})")
        return encoded
    except BadRequestError as exc:
        # Key with this name already exists — not a fatal error
        print(f"  ⚠️  API key may already exist: {exc}")
        return ""


def create_kibana_service_token(es: Elasticsearch) -> str:
    """Create a Kibana service account token for ES 8.11+ compatibility.

    ES 8.11 forbids using the elastic superuser as the Kibana credential.
    The service account token is the supported replacement.

    Returns:
        The token value to store in .env as KIBANA_SERVICE_TOKEN.
    """
    print("\n── Creating Kibana service account token ───────────────────")
    try:
        response = es.perform_request(
            method="POST",
            path="/_security/service/elastic/kibana/credential/token/kibana-token-1",
        )
        token_value = response.body["token"]["value"]
        print("  ✅ Kibana service account token created")
        return token_value
    except Exception as exc:
        # Token may already exist — not fatal; Kibana will use the existing token
        print(f"  ⚠️  Token may already exist (safe to ignore): {exc}")
        return ""


def print_summary(api_key: str, kibana_token: str) -> None:
    """Print a summary of what was created and next steps."""
    print("\n── Summary ─────────────────────────────────────────────────")
    print("  6 roles created:   security_analyst, senior_security_engineer,")
    print("                     ml_operations, compliance_officer,")
    print("                     system_administrator, read_only_auditor")
    print("  6 test users:      test_analyst, test_engineer, test_ml_ops,")
    print("                     test_compliance, test_sysadmin, test_auditor")
    if api_key:
        print(f"\n  ⚠️  Add this to your .env file:")
        print(f"  ELASTIC_API_KEY={api_key}")
    if kibana_token:
        print(f"\n  ⚠️  Add this to your .env file (required for Kibana 8.11+):")
        print(f"  KIBANA_SERVICE_TOKEN={kibana_token}")
        print("  Then restart Kibana: docker compose restart kibana")
    print("\n  Run RBAC verification tests:")
    print("  docker compose --profile dev run --rm dev pytest tests/test_rbac.py -v -m integration")
    print("────────────────────────────────────────────────────────────\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full RBAC bootstrap sequence."""
    print(f"Connecting to Elasticsearch at {_HOST} ...")
    es = _connect()

    # Confirm the cluster is reachable before doing anything
    if not es.ping():
        print("ERROR: Cannot reach Elasticsearch. Is the stack running?")
        print("  docker compose up -d elasticsearch")
        sys.exit(1)

    info = es.info()
    print(f"Connected — cluster: {info['cluster_name']}, version: {info['version']['number']}")

    create_roles(es)
    create_users(es)
    api_key = create_api_key(es)
    kibana_token = create_kibana_service_token(es)
    print_summary(api_key, kibana_token)


if __name__ == "__main__":
    main()
