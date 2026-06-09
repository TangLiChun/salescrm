#!/usr/bin/env bash
# 备份 docker compose 内的 Postgres 数据库（pg_dump 自定义格式，含压缩）。
# 用法：
#   scripts/backup_db.sh [备份目录]      # 默认 ./backups
# 建议配合 cron 每日执行，并把备份目录同步到异地存储。
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${1:-backups}"
POSTGRES_USER="${POSTGRES_USER:-salescrm}"
POSTGRES_DB="${POSTGRES_DB:-salescrm}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/salescrm_${STAMP}.dump"

docker compose exec -T postgres pg_dump \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "$OUT"

# 简单校验：自定义格式以 PGDMP 开头
head -c 5 "$OUT" | grep -q "PGDMP" || {
  echo "备份文件校验失败：$OUT" >&2
  exit 1
}

# 清理超过 KEEP_DAYS 天的旧备份
find "$BACKUP_DIR" -name 'salescrm_*.dump' -mtime "+${KEEP_DAYS}" -delete

echo "备份完成：$OUT ($(du -h "$OUT" | cut -f1))"
