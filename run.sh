#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Canonical persistent cache requested for this service.
export WIKIMEDIA_IMAGE_CACHE="${WIKIMEDIA_IMAGE_CACHE:-/Volumes/Extreme SSD/webmaster-ai/POJO_PROJECT/data/images}"

if [[ ! -d "$WIKIMEDIA_IMAGE_CACHE" ]]; then
  echo "ERROR: Wikimedia image cache does not exist:"
  echo "       $WIKIMEDIA_IMAGE_CACHE"
  echo "Mount the Extreme SSD or create the directory first."
  exit 1
fi

mkdir -p "$WIKIMEDIA_IMAGE_CACHE"/{people,movies,shows,places,organizations,events,other}

echo "WIKIMEDIA_IMAGE_CACHE=$WIKIMEDIA_IMAGE_CACHE"

exec uvicorn app:app --host "$HOST" --port "$PORT"
