#!/usr/bin/env bash
# 从 backup_db.sh 生成的 .dump 恢复数据库。会覆盖现有数据，请先确认。
# 用法：
#   scripts/restore_db.sh backups/salescrm_20260610_120000.dump
set -euo pipefail

cd "$(dirname "$0")/.."

DUMP_FILE="${1:?用法: scripts/restore_db.sh <dump 文件>}"
POSTGRES_USER="${POSTGRES_USER:-salescrm}"
POSTGRES_DB="${POSTGRES_DB:-salescrm}"

[ -f "$DUMP_FILE" ] || { echo "找不到文件：$DUMP_FILE" >&2; exit 1; }

read -r -p "将用 $DUMP_FILE 覆盖数据库 $POSTGRES_DB，输入 yes 继续: " CONFIRM
[ "$CONFIRM" = "yes" ] || { echo "已取消"; exit 1; }

# 停应用避免恢复期间写入
docker compose stop salescrm pi-agent

docker compose exec -T postgres pg_restore \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < "$DUMP_FILE"

docker compose start salescrm pi-agent

echo "恢复完成。请登录验证数据。"
