#!/usr/bin/env bash
# =============================================================================
# generate_certs.sh — Generate self-signed TLS certificates for Elasticsearch
# =============================================================================
# Produces a local Certificate Authority (CA) and a server certificate for
# Elasticsearch.  These enable TLS 1.3 on the ES HTTP and transport layers,
# satisfying PCI DSS v4.0 Requirement 4.2.1 (strong cryptography in transit).
#
# Usage:
#   chmod +x scripts/generate_certs.sh
#   ./scripts/generate_certs.sh
#
# Output (in certs/):
#   ca.crt          — CA certificate (import into browser/client trust stores)
#   ca.key          — CA private key (keep secret — never commit)
#   elasticsearch.crt  — ES server certificate signed by the CA
#   elasticsearch.key  — ES server private key (keep secret — never commit)
#
# After running this script:
#   1. Uncomment the TLS sections in docker-compose.yml
#   2. Restart the stack: docker compose down && docker compose up -d
#   3. Update ELASTIC_HOST in .env to https://localhost:9200
#   4. Update all elasticsearch-py clients to use verify_certs=True
#      and ca_certs="certs/ca.crt"
#
# NOTE: Self-signed certificates are suitable for the prototype and local
# development.  Production deployments must use certificates issued by a
# trusted CA (e.g. Let's Encrypt, AWS ACM, or a corporate PKI).
# =============================================================================

set -euo pipefail

CERTS_DIR="$(dirname "$0")/../certs"
mkdir -p "$CERTS_DIR"

echo "Generating TLS certificates in $CERTS_DIR ..."

# ---------------------------------------------------------------------------
# 1. Generate CA private key and self-signed certificate
# ---------------------------------------------------------------------------
openssl genrsa -out "$CERTS_DIR/ca.key" 4096

openssl req -new -x509 -days 3650 \
  -key "$CERTS_DIR/ca.key" \
  -out "$CERTS_DIR/ca.crt" \
  -subj "/C=AU/ST=Queensland/L=Brisbane/O=Meridian Financial Services/CN=Meridian-CA"

echo "  ✅ CA certificate generated: certs/ca.crt"

# ---------------------------------------------------------------------------
# 2. Generate Elasticsearch server key and CSR
# ---------------------------------------------------------------------------
openssl genrsa -out "$CERTS_DIR/elasticsearch.key" 4096

openssl req -new \
  -key "$CERTS_DIR/elasticsearch.key" \
  -out "$CERTS_DIR/elasticsearch.csr" \
  -subj "/C=AU/ST=Queensland/L=Brisbane/O=Meridian Financial Services/CN=elasticsearch"

# ---------------------------------------------------------------------------
# 3. Sign the ES certificate with the CA (valid 2 years)
# ---------------------------------------------------------------------------
# SAN includes both the Docker service name and localhost so the cert works
# for both inter-container and host-to-container connections.
cat > "$CERTS_DIR/elasticsearch.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:elasticsearch,DNS:localhost,IP:127.0.0.1
EOF

openssl x509 -req -days 730 \
  -in "$CERTS_DIR/elasticsearch.csr" \
  -CA "$CERTS_DIR/ca.crt" \
  -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial \
  -out "$CERTS_DIR/elasticsearch.crt" \
  -extfile "$CERTS_DIR/elasticsearch.ext"

# Clean up intermediate files
rm -f "$CERTS_DIR/elasticsearch.csr" "$CERTS_DIR/elasticsearch.ext" "$CERTS_DIR/ca.srl"

echo "  ✅ ES server certificate generated: certs/elasticsearch.crt"

# ---------------------------------------------------------------------------
# 4. Set restrictive permissions on private keys
# ---------------------------------------------------------------------------
chmod 600 "$CERTS_DIR/ca.key" "$CERTS_DIR/elasticsearch.key"

echo ""
echo "Done. To enable TLS on the stack, uncomment the TLS sections in"
echo "docker-compose.yml and restart: docker compose down && docker compose up -d"
echo ""
echo "Production note: replace these self-signed certificates with certificates"
echo "issued by a trusted CA before any production deployment."
