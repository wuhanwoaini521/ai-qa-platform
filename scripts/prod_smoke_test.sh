#!/usr/bin/env bash
set -euo pipefail

# AI QA Platform — Production Stack Smoke Test
# Usage: ./scripts/prod_smoke_test.sh [API_BASE_URL]

API_URL="${1:-http://127.0.0.1:8000}"
echo "=== AI QA Platform: Smoke Test against $API_URL ==="

# 1. Health Probe
echo -n "Checking /api/health... "
HEALTH_RESP=$(curl -s -f "${API_URL}/api/health")
echo "OK"

# 2. Liveness Probe
echo -n "Checking /api/health/live... "
curl -s -f "${API_URL}/api/health/live" >/dev/null
echo "OK"

# 3. Readiness Probe
echo -n "Checking /api/health/ready... "
curl -s -f "${API_URL}/api/health/ready" >/dev/null
echo "OK"

# 4. Prometheus Metrics
echo -n "Checking /api/metrics... "
METRICS=$(curl -s -f "${API_URL}/api/metrics")
if [[ "$METRICS" == *"ai_qa_platform_uptime_seconds"* ]]; then
    echo "OK (Metrics format verified)"
else
    echo "FAILED (Metrics format mismatch)"
    exit 1
fi

# 5. Worker Cluster Status
echo -n "Checking /api/workers/cluster-status... "
CLUSTER=$(curl -s -f "${API_URL}/api/workers/cluster-status")
echo "OK"

echo "=== All Production Smoke Tests Passed! ==="
