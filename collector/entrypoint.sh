#!/usr/bin/env bash
set -euo pipefail
echo "[collector] starting… interval=${COLLECT_INTERVAL:-3600}s"

try_ingest() {
  local p="$1"
  if [ -f "$p" ]; then
    echo "[collector] ingesting to Postgres from $p"
    METRICS_JSON_PATH="$p" python - <<'PY'
from collector.db_write import write_json
import os
path = os.environ.get("METRICS_JSON_PATH")
if not path:
    raise SystemExit("METRICS_JSON_PATH not set")
try:
    n = write_json(path)
    print(f"[collector] wrote {n} rows to Postgres")
except Exception as e:
    print(f"[collector] Postgres write failed: {e}")
PY
  fi
}

while true; do
  echo "[collector] run at $(date -Iseconds)"
  python -m collector.metrics_collector || echo "[collector] run failed (non-fatal)"

  # Try common snapshot locations
  if [ -n "${METRICS_JSON_PATH:-}" ] && [ -f "$METRICS_JSON_PATH" ]; then
    try_ingest "$METRICS_JSON_PATH"
  else
    try_ingest "/data/device_metrics.json"
    try_ingest "/app/device_metrics.json"
    try_ingest "/app/collector/device_metrics.json"
  fi

  echo "[collector] sleeping ${COLLECT_INTERVAL:-3600}s"
  sleep "${COLLECT_INTERVAL:-3600}"
done
