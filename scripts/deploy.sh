#!/usr/bin/env bash
set -euo pipefail

# AI QA Platform — Production Deployment Helper
# Usage: ./scripts/deploy.sh [--build] [--scale-workers N]

BUILD_FLAG=""
WORKER_COUNT=2

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build)
            BUILD_FLAG="--build"
            shift
            ;;
        --scale-workers)
            WORKER_COUNT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== AI QA Platform: Production Deployment ==="
echo "Building / Starting containers with Docker Compose..."

docker compose up -d $BUILD_FLAG --scale worker="$WORKER_COUNT"

echo "Waiting for services to become healthy..."
sleep 5

API_READY=false
for i in {1..30}; do
    if curl -s -f http://127.0.0.1:8000/api/health/ready >/dev/null 2>&1 || curl -s -f http://localhost:8000/api/health/ready >/dev/null 2>&1; then
        API_READY=true
        break
    fi
    echo "Waiting for API readiness ($i/30)..."
    sleep 2
done

if [ "$API_READY" = true ]; then
    echo "AI QA Platform deployed and healthy!"
    echo "Web UI:     http://localhost:3000 (or http://localhost)"
    echo "API Docs:   http://localhost:8000/docs"
    echo "Metrics:    http://localhost:8000/api/metrics"
    echo "MinIO UI:   http://localhost:9001"
else
    echo "Deployment warning: API did not report ready within 60s. Check logs: docker compose logs api"
fi
