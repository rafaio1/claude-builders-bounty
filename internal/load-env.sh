#!/usr/bin/env bash
# Load GhostCLI + Bybit into the current shell. Never echo secret values.
# Canonical Bybit file: /root/.automaton/bybit-murre.env

if [ "${AGENTIC_ENV_LOADED:-}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi

set -a
if [ -f /root/.automaton/.env ]; then
  # shellcheck disable=SC1091
  . /root/.automaton/.env
fi
if [ -f /opt/murre/.env ]; then
  # shellcheck disable=SC1091
  . /opt/murre/.env
fi
if [ -f /root/.automaton/bybit-murre.env ]; then
  # Canonical Bybit keys win over the /opt/murre copy.
  # shellcheck disable=SC1091
  . /root/.automaton/bybit-murre.env
fi
set +a

export BYBIT_ENV_FILE="${BYBIT_ENV_FILE:-/root/.automaton/bybit-murre.env}"
export BYBIT_API_KEY="${BYBIT_API_KEY:-${BYBIT_REAL_API_KEY:-}}"
export BYBIT_API_SECRET="${BYBIT_API_SECRET:-${BYBIT_REAL_API_SECRET:-}}"
export BYBIT_MODE="${BYBIT_MODE:-live}"
export BYBIT_CATEGORY="${BYBIT_CATEGORY:-spot}"
export AGENTIC_ENV_LOADED=1
