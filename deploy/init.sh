#!/usr/bin/env bash
# Prepare .env.prod for a deployment.
#
# Derives ES_BASIC_AUTH from ELASTIC_PASSWORD so the value Caddy injects can
# never drift out of sync with the password Elasticsearch is actually using —
# a mismatch there produces a 401 on every dashboard poll and looks like the
# cluster is down.
#
#     ./deploy/init.sh
#
# Safe to re-run: it recalculates and rewrites only ES_BASIC_AUTH.

set -euo pipefail

ENV_FILE="${1:-.env.prod}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "error: $ENV_FILE not found."
    echo "       cp .env.prod.example $ENV_FILE   and fill it in first."
    exit 1
fi

# shellcheck disable=SC1090
ELASTIC_PASSWORD="$(grep -E '^ELASTIC_PASSWORD=' "$ENV_FILE" | cut -d= -f2- || true)"

if [[ -z "$ELASTIC_PASSWORD" ]]; then
    echo "error: ELASTIC_PASSWORD is empty in $ENV_FILE."
    echo "       generate one:  openssl rand -base64 24"
    exit 1
fi

if [[ ${#ELASTIC_PASSWORD} -lt 12 ]]; then
    echo "error: ELASTIC_PASSWORD is only ${#ELASTIC_PASSWORD} characters."
    echo "       This cluster is internet-facing. Use at least 12."
    exit 1
fi

BASIC_AUTH="$(printf 'elastic:%s' "$ELASTIC_PASSWORD" | base64 | tr -d '\n')"

if grep -qE '^ES_BASIC_AUTH=' "$ENV_FILE"; then
    # macOS and GNU sed disagree on -i; write through a temp file instead.
    tmp="$(mktemp)"
    sed "s|^ES_BASIC_AUTH=.*|ES_BASIC_AUTH=${BASIC_AUTH}|" "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"
else
    printf '\nES_BASIC_AUTH=%s\n' "$BASIC_AUTH" >> "$ENV_FILE"
fi

chmod 600 "$ENV_FILE"

DOMAIN="$(grep -E '^DOMAIN=' "$ENV_FILE" | cut -d= -f2- || true)"

echo "ES_BASIC_AUTH written to $ENV_FILE (permissions set to 600)."
echo
echo "Next:"
echo "  1. Point a DNS A record for ${DOMAIN:-<DOMAIN>} at this server."
echo "  2. docker compose -f docker-compose.prod.yml --env-file $ENV_FILE up -d --build"
echo "  3. Watch certificate issuance:  docker compose -f docker-compose.prod.yml logs -f caddy"
