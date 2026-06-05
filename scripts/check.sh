#!/usr/bin/env bash
# 检查 Sales CRM 是否正常运行（部署后或日常巡检）
#
#   ./scripts/check.sh          详细输出，失败时 exit 1
#   ./scripts/check.sh --quiet  仅 exit code，无输出
#   ./scripts/check.sh --quick    仅容器 + HTTP（deploy 等待用）
#   ./scripts/check.sh --quick --quiet
#
# 环境变量：
#   APP_PORT        对外端口（默认 8000）
#   SMOKE_RETRIES   冒烟重试次数（默认 3）
#   SMOKE_USER      冒烟登录用户名（默认 admin，见 smoke_check.py）
#   SMOKE_PASSWORD  冒烟登录密码（默认 admin123）

set -euo pipefail

QUIET=0
QUICK=0
for arg in "$@"; do
  case "${arg}" in
    --quiet) QUIET=1 ;;
    --quick) QUICK=1 ;;
  esac
done

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
  echo "ERROR: $*" >&2
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

health_body_valid() {
  local body="$1"
  [[ -n "${body}" ]] \
    && echo "${body}" | grep -q '"ok"[[:space:]]*:[[:space:]]*true' \
    && echo "${body}" | grep -q '"db"[[:space:]]*:[[:space:]]*true' \
    && echo "${body}" | grep -q '"schema"[[:space:]]*:[[:space:]]*true'
}

curl_health_body_host() {
  curl -fsS --max-time 5 "http://127.0.0.1:${APP_PORT}/health" 2>/dev/null
}

curl_health_body_internal() {
  # 容器已 running 但 uvicorn 仍在 import 时，宿主机端口可能尚未就绪；用容器内探测更可靠
  $DOCKER exec "${CONTAINER}" python -c '
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5).read().decode())
' 2>/dev/null
}

curl_health_body() {
  local attempt body
  for attempt in 1 2 3; do
    body="$(curl_health_body_host)"
    if health_body_valid "${body}"; then
      printf '%s' "${body}"
      return 0
    fi
    body="$(curl_health_body_internal)"
    if health_body_valid "${body}"; then
      printf '%s' "${body}"
      return 0
    fi
    sleep 1
  done
  return 1
}

check_health_http() {
  local url="http://127.0.0.1:${APP_PORT}/health"
  local body

  body="$(curl_health_body)" || {
    show_logs
    fail "无法访问 ${url}（服务未监听或启动失败）"
  }

  if ! health_body_valid "${body}"; then
    say "响应: ${body}"
    show_logs
    fail "健康检查未通过（ok/db/schema 需均为 true）"
  fi

  say "HTTP: ${url} — ok"
  say "响应: ${body}"
}

check_smoke() {
  local -a smoke_exec_env=(-e PYTHONPATH=/app)
  [[ -n "${SMOKE_USER:-}" ]] && smoke_exec_env+=(-e "SMOKE_USER=${SMOKE_USER}")
  [[ -n "${SMOKE_PASSWORD:-}" ]] && smoke_exec_env+=(-e "SMOKE_PASSWORD=${SMOKE_PASSWORD}")
  local max_attempts="${SMOKE_RETRIES:-3}"
  local attempt output
  for attempt in $(seq 1 "${max_attempts}"); do
    if $DOCKER exec "${smoke_exec_env[@]}" "${CONTAINER}" python /app/scripts/smoke_check.py >/dev/null 2>&1; then
      say "冒烟: scripts/smoke_check.py — ok"
      return 0
    fi
    sleep 2
  done
  say "API 冒烟测试失败："
  output="$($DOCKER exec "${smoke_exec_env[@]}" "${CONTAINER}" python /app/scripts/smoke_check.py 2>&1 || true)"
  [[ -n "${output}" ]] && echo "${output}"
  show_logs
  fail "关键 API / 数据库查询异常（如缺表导致 500）"
}

check_docker_health() {
  local h
  h="$($DOCKER inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER}" 2>/dev/null || echo unknown)"
  case "${h}" in
    healthy)
      say "Docker health: healthy"
      ;;
    unhealthy)
      # deploy 刚完成时 Docker 内置 health 可能尚未从 starting 变 healthy
      say "Docker health: unhealthy（HTTP 已通过，继续）"
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
  if [[ "$QUICK" -eq 0 ]]; then
    check_smoke
    check_docker_health
  fi
  [[ "$QUIET" -eq 0 ]] && echo "" && echo "OK: Sales CRM 运行正常"
}

main "$@"
