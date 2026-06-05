#!/usr/bin/env bash
# 检查 Sales CRM 是否正常运行（部署后或日常巡检）
#
#   ./scripts/check.sh          详细输出，失败时 exit 1
#   ./scripts/check.sh --quiet  仅 exit code，无输出

set -euo pipefail

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

APP_PORT="${APP_PORT:-8000}"
CONTAINER="${CONTAINER:-salescrm}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]] && docker info >/dev/null 2>&1; then
  DOCKER="docker"
elif [[ "$(id -u)" -eq 0 ]]; then
  DOCKER="docker"
else
  DOCKER="sudo docker"
fi

say() { [[ "$QUIET" -eq 0 ]] && echo "$*"; }
fail() {
  [[ "$QUIET" -eq 0 ]] && echo "ERROR: $*" >&2
  exit 1
}

show_logs() {
  [[ "$QUIET" -eq 1 ]] && return
  echo ""
  echo "--- 最近日志 (docker compose logs --tail 40) ---"
  (cd "${APP_DIR}" && $DOCKER compose logs --tail 40) 2>/dev/null || \
    $DOCKER logs --tail 40 "${CONTAINER}" 2>/dev/null || true
  echo "---"
}

check_container() {
  if ! $DOCKER inspect "${CONTAINER}" >/dev/null 2>&1; then
    fail "容器 ${CONTAINER} 不存在，请先运行 ./scripts/deploy.sh"
  fi

  local status restarting exit_code
  status="$($DOCKER inspect -f '{{.State.Status}}' "${CONTAINER}" 2>/dev/null || echo unknown)"
  restarting="$($DOCKER inspect -f '{{.State.Restarting}}' "${CONTAINER}" 2>/dev/null || echo false)"
  exit_code="$($DOCKER inspect -f '{{.State.ExitCode}}' "${CONTAINER}" 2>/dev/null || echo 0)"

  if [[ "${restarting}" == "true" || "${status}" == "restarting" ]]; then
    say "容器状态: restarting（进程反复崩溃）"
    show_logs
    fail "应用在崩溃重启循环中，请查看上方日志"
  fi

  if [[ "${status}" != "running" ]]; then
    say "容器状态: ${status} (exit code ${exit_code})"
    show_logs
    fail "容器未处于 running 状态"
  fi

  say "容器: ${CONTAINER} — running"
}

check_health_http() {
  local url="http://127.0.0.1:${APP_PORT}/health"
  local body http_code

  body="$(curl -fsS --max-time 5 "${url}" 2>/dev/null)" || {
    show_logs
    fail "无法访问 ${url}（服务未监听或启动失败）"
  }

  http_code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 5 "${url}" 2>/dev/null || echo 000)"
  if [[ "${http_code}" != "200" ]]; then
    show_logs
    fail "健康检查 HTTP ${http_code}，期望 200"
  fi

  if ! echo "${body}" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
    say "响应: ${body}"
    show_logs
    fail "健康检查 ok != true（数据库或服务异常）"
  fi

  if ! echo "${body}" | grep -q '"db"[[:space:]]*:[[:space:]]*true'; then
    say "响应: ${body}"
    fail "数据库不可用 (db != true)"
  fi

  if ! echo "${body}" | grep -q '"schema"[[:space:]]*:[[:space:]]*true'; then
    say "响应: ${body}"
    show_logs
    fail "数据库表结构不完整 (schema != true)，请重新部署以执行 init_db"
  fi

  say "HTTP: ${url} — ok"
  say "响应: ${body}"
}

check_smoke() {
  if ! $DOCKER exec "${CONTAINER}" python scripts/smoke_check.py >/dev/null 2>&1; then
    say "API 冒烟测试失败："
    $DOCKER exec "${CONTAINER}" python scripts/smoke_check.py 2>&1 || true
    show_logs
    fail "关键 API / 数据库查询异常（如缺表导致 500）"
  fi
  say "冒烟: scripts/smoke_check.py — ok"
}

check_docker_health() {
  local h
  h="$($DOCKER inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER}" 2>/dev/null || echo unknown)"
  case "${h}" in
    healthy)
      say "Docker health: healthy"
      ;;
    unhealthy)
      show_logs
      fail "Docker 内置健康检查为 unhealthy"
      ;;
    starting)
      say "Docker health: starting（仍在启动，可稍后再查）"
      ;;
    none)
      say "Docker health: 未配置（已用 HTTP /health 验证）"
      ;;
  esac
}

main() {
  cd "${APP_DIR}"
  check_container
  check_health_http
  check_smoke
  check_docker_health
  [[ "$QUIET" -eq 0 ]] && echo "" && echo "OK: Sales CRM 运行正常"
}

main "$@"
