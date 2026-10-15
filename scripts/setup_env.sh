#!/usr/bin/env bash
set +H

# Load AIDP lab credentials from a file outside the repo (default ~/.cnc-demo-credentials)
# so secrets are never committed. Use: source scripts/setup_env.sh [credentials-file]

CREDS_FILE="${1:-$HOME/.cnc-demo-credentials}"

if [[ ! -f "$CREDS_FILE" ]]; then
    echo "Credentials file not found: $CREDS_FILE" >&2
    echo "Create it from scripts/env.template or copy the provided .cnc-demo-credentials file." >&2
    return 1 2>/dev/null || exit 1
fi

source "$CREDS_FILE"

export DPE_JAVA_HOME="${DPE_JAVA_HOME:-/home/betalab/workspace/tk/openjdk/jdk-27}"

if [[ -n "$DPE_CLI" ]]; then
    DPE_BIN_DIR=$(dirname "$DPE_CLI")
    export PATH="$DPE_BIN_DIR:$PATH"
fi

dpe() {
    JAVA_HOME="$DPE_JAVA_HOME" "$DPE_CLI" "$@"
}

if [[ -n "$TRINO_USER" && -n "$TRINO_PASS" ]]; then
    AIDP_MCP_AUTH=$(printf '%s:%s' "$TRINO_USER" "$TRINO_PASS" | base64 | tr -d '\n')
    export AIDP_MCP_AUTH
fi

export PYSPARK_PYTHON=python3
export PYSPARK_DRIVER_PYTHON=python3

echo "Environment configured for CNC Spindle Health demo." >&2
echo "  JAVA_HOME=${JAVA_HOME:-<system default>}" >&2
echo "  S3_ENDPOINT=$S3_ENDPOINT" >&2
echo "  TRINO_HOST=$TRINO_HOST" >&2
echo "  AIDP_MCP_URL=$AIDP_MCP_URL" >&2
echo "  ELASTIC_ENDPOINT=$ELASTIC_ENDPOINT" >&2
