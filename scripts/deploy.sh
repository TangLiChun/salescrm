#!/usr/bin/env bash
# Run on the VPS after git pull (no SSH from your laptop).
#
#   cd /opt/salescrm
#   git pull
#   ./scripts/deploy.sh
#
# Optional: APP_PORT=8000 ./scripts/deploy.sh

set -euo pipefail

cd "$(dirname "$0")/.."
export APP_PORT="${APP_PORT:-8000}"

echo "==> Building and starting Sales CRM (port ${APP_PORT})..."
docker compose up -d --build --remove-orphans
docker compose ps

IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')"
echo ""
echo "Done. Open: http://${IP}:${APP_PORT}/"
echo "Default login: admin / admin123"
echo "Logs: docker compose logs -f"
