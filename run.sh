#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

if [[ -z "${WIKIMEDIA_IMAGE_CACHE:-}" ]]; then
  DEFAULT_CACHE="/Volumes/Extreme SSD/webmaster-ai/POJO_PROJECT/data/images"
  if [[ -d "$DEFAULT_CACHE" ]]; then
    export WIKIMEDIA_IMAGE_CACHE="$DEFAULT_CACHE"
  else
    export WIKIMEDIA_IMAGE_CACHE="./data/images"
  fi
fi

echo "WIKIMEDIA_IMAGE_CACHE=$WIKIMEDIA_IMAGE_CACHE"

exec uvicorn app:app --host "$HOST" --port "$PORT"
