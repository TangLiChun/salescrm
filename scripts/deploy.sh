#!/usr/bin/env bash
# Sales CRM — VPS 一键安装 / 更新（在服务器上执行，无需本机 SSH 部署）
#
# 首次安装：
#   git clone https://github.com/TangLiChun/salescrm.git /opt/salescrm
#   cd /opt/salescrm && sudo ./scripts/deploy.sh
#
# 之后更新：
#   cd /opt/salescrm && sudo ./scripts/deploy.sh
#
# 也可指定目录与分支：
#   APP_DIR=/opt/salescrm GIT_BRANCH=main ./scripts/deploy.sh
#
# 环境变量：
#   APP_DIR         安装目录（默认：脚本所在仓库根目录，或 /opt/salescrm）
#   APP_PORT        对外端口（默认 8000）
#   GIT_REPO        仓库地址
#   GIT_BRANCH      分支（默认 main）
#   SKIP_PULL=1     跳过 git pull（仅重建容器）
#   FORCE_REBUILD=1 构建镜像时使用 --no-cache
#   SKIP_PI=1       跳过 Pi Coding Agent 安装与配置
#
# 部署验证（失败则 exit 1 并打印日志）：
#   1. docker build 阶段导入 app（Dockerfile）— 捕获启动语法/路由错误
#   2. 容器 running，非 crash loop
#   3. GET /health — db + schema（缺表会失败）
#   4. 容器内 smoke_check.py — 登录并探测 email-templates 等 API

set -euo pipefail

GIT_REPO="${GIT_REPO:-https://github.com/TangLiChun/salescrm.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
APP_PORT="${APP_PORT:-8000}"
SKIP_PULL="${SKIP_PULL:-0}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"
SKIP_PI="${SKIP_PI:-0}"
PI_ENV_FILE=""
PI_SETUP_OK=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 若从空目录调用且尚未 clone，使用 /opt/salescrm
if [[ ! -f "${DEFAULT_APP_DIR}/docker-compose.yml" && -z "${APP_DIR:-}" ]]; then
  APP_DIR="/opt/salescrm"
else
  APP_DIR="${APP_DIR:-${DEFAULT_APP_DIR}}"
fi

log() { echo "==> $*"; }
warn() { echo "WARNING: $*" >&2; }

if [[ "$(id -u)" -ne 0 ]]; then
  warn "建议使用 root 或 sudo 运行（安装 Docker 需要权限）"
  SUDO="sudo"
else
  SUDO=""
fi

run_apt() {
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get "$@"
  else
    warn "未检测到 apt-get，请手动安装: git curl ca-certificates docker"
    return 1
  fi
}

install_system_packages() {
  log "安装系统依赖 (git, curl, ca-certificates)..."
  run_apt update -qq
  run_apt install -y -qq git curl ca-certificates
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker 已安装: $(docker --version)"
    return
  fi

  log "安装 Docker..."
  install_system_packages || true
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable docker >/dev/null 2>&1 || true
  $SUDO systemctl start docker >/dev/null 2>&1 || true

  if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose 插件未就绪，请检查 Docker 安装" >&2
    exit 1
  fi
  log "Docker 安装完成: $(docker --version)"
}

ensure_repo() {
  if [[ -f "${APP_DIR}/docker-compose.yml" ]]; then
    log "使用已有目录: ${APP_DIR}"
    cd "${APP_DIR}"
    if [[ -d .git ]]; then
      if [[ "${SKIP_PULL}" != "1" ]]; then
        log "拉取最新代码 (${GIT_BRANCH})..."
        git fetch origin "${GIT_BRANCH}"
        git checkout "${GIT_BRANCH}" 2>/dev/null || git checkout -b "${GIT_BRANCH}" "origin/${GIT_BRANCH}"
        git pull --ff-only origin "${GIT_BRANCH}"
      else
        log "跳过 git pull (SKIP_PULL=1)"
      fi
    else
      warn "目录存在但非 git 仓库，跳过 git pull"
    fi
    return
  fi

  log "首次安装：clone 仓库到 ${APP_DIR} ..."
  install_system_packages
  $SUDO mkdir -p "$(dirname "${APP_DIR}")"
  if [[ ! -d "${APP_DIR}" ]]; then
    $SUDO git clone --branch "${GIT_BRANCH}" --depth 1 "${GIT_REPO}" "${APP_DIR}"
  else
    $SUDO git clone --branch "${GIT_BRANCH}" --depth 1 "${GIT_REPO}" "${APP_DIR}.tmp"
    $SUDO cp -a "${APP_DIR}.tmp/." "${APP_DIR}/"
    $SUDO rm -rf "${APP_DIR}.tmp"
  fi
  cd "${APP_DIR}"
}

deploy_compose() {
  log "构建镜像 (port ${APP_PORT})..."
  export APP_PORT
  local build_args=()
  if [[ "${FORCE_REBUILD}" == "1" ]]; then
    build_args+=(--no-cache)
    log "FORCE_REBUILD=1 — 无缓存构建"
  fi
  if ! $SUDO env APP_PORT="${APP_PORT}" docker compose build "${build_args[@]}"; then
    echo "ERROR: docker compose build 失败" >&2
    show_failure_logs
    exit 1
  fi

  log "启动容器..."
  if ! $SUDO env APP_PORT="${APP_PORT}" docker compose up -d --remove-orphans; then
    echo "ERROR: docker compose up 失败" >&2
    show_failure_logs
    exit 1
  fi
  echo ""
  $SUDO docker compose ps
}

show_failure_logs() {
  echo ""
  echo "========== 部署失败 · 最近日志 =========="
  (cd "${APP_DIR}" && $SUDO docker compose logs --tail 60) 2>/dev/null || true
  echo "========================================="
  echo "排查: cd ${APP_DIR} && ./scripts/check.sh"
  echo "      cd ${APP_DIR} && docker compose logs -f"
}

wait_healthy() {
  log "等待服务就绪并验证..."
  local i
  for i in $(seq 1 45); do
    if APP_PORT="${APP_PORT}" "${SCRIPT_DIR}/check.sh" --quiet 2>/dev/null; then
      log "健康检查通过"
      return 0
    fi
    sleep 2
  done
  echo ""
  echo "ERROR: 部署完成但服务未正常运行（超时 ${i}×2s）" >&2
  APP_PORT="${APP_PORT}" "${SCRIPT_DIR}/check.sh" || true
  exit 1
}

node_major_version() {
  if ! command -v node >/dev/null 2>&1; then
    echo 0
    return
  fi
  node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0
}

install_node() {
  local major
  major="$(node_major_version)"
  if [[ "${major}" -ge 18 ]]; then
    log "Node.js 已安装: $(node -v)"
    return 0
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    warn "无法自动安装 Node.js（需要 18+），请手动安装后重新运行 deploy.sh"
    return 1
  fi

  log "安装 Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO bash -
  run_apt install -y -qq nodejs
  major="$(node_major_version)"
  if [[ "${major}" -lt 18 ]]; then
    warn "Node.js 版本过低 ($(node -v 2>/dev/null || echo none))，Pi 需要 18+"
    return 1
  fi
  log "Node.js 安装完成: $(node -v)"
}

fetch_agent_token() {
  (cd "${APP_DIR}" && $SUDO docker exec salescrm python -c \
    "from app.settings_store import get_agent_api_token; print(get_agent_api_token())" 2>/dev/null) \
    | tr -d '\r' | head -n 1
}

write_pi_env_file() {
  local token="$1"
  PI_ENV_FILE="${APP_DIR}/.pi-env"
  umask 077
  cat > "${PI_ENV_FILE}" <<EOF
# Sales CRM Pi Agent — 由 deploy.sh 自动生成，请勿提交到 git
export SALESCRM_URL="http://127.0.0.1:${APP_PORT}"
export SALESCRM_TOKEN="${token}"
EOF
  chmod 600 "${PI_ENV_FILE}"
  $SUDO chown "$(id -un)":"$(id -gn)" "${PI_ENV_FILE}" 2>/dev/null || true
}

ensure_pi_env_autoload() {
  local marker="# salescrm-pi-env"
  local line="[[ -f \"${APP_DIR}/.pi-env\" ]] && source \"${APP_DIR}/.pi-env\""
  local rc="${HOME}/.bashrc"
  [[ -f "${rc}" ]] || return 0
  if grep -qF "${marker}" "${rc}" 2>/dev/null; then
    return 0
  fi
  {
    echo ""
    echo "${marker}"
    echo "${line}"
  } >> "${rc}"
}

install_pi_cli() {
  if command -v pi >/dev/null 2>&1; then
    log "Pi CLI 已安装: $(pi --version 2>/dev/null | head -n 1 || echo pi)"
    return 0
  fi
  log "安装 Pi Coding Agent CLI..."
  npm install -g @mariozechner/pi-coding-agent
  command -v pi >/dev/null 2>&1
}

install_pi_extension() {
  log "安装 Sales CRM Pi 扩展包..."
  pi install "${APP_DIR}/integrations/pi"
}

verify_pi_agent_api() {
  local token="$1"
  curl -fsS --max-time 10 \
    -H "Authorization: Bearer ${token}" \
    "http://127.0.0.1:${APP_PORT}/api/agent/health" >/dev/null
}

setup_pi_agent() {
  if [[ "${SKIP_PI}" == "1" ]]; then
    log "跳过 Pi Agent 安装 (SKIP_PI=1)"
    return 0
  fi

  if [[ ! -d "${APP_DIR}/integrations/pi" ]]; then
    warn "未找到 ${APP_DIR}/integrations/pi，跳过 Pi 安装"
    return 0
  fi

  log "配置 Pi Coding Agent..."
  if ! install_node; then
    warn "Pi Agent 未安装：Node.js 不可用"
    return 0
  fi

  local token
  token="$(fetch_agent_token)"
  if [[ -z "${token}" ]]; then
    warn "无法读取 Agent API Token，跳过 Pi 配置"
    return 0
  fi

  write_pi_env_file "${token}"
  # shellcheck disable=SC1090
  set +u
  source "${PI_ENV_FILE}"
  set -u

  if ! install_pi_cli; then
    warn "Pi CLI 安装失败，已写入 ${PI_ENV_FILE}，可稍后手动: npm i -g @mariozechner/pi-coding-agent"
    return 0
  fi

  if ! install_pi_extension; then
    warn "Pi 扩展安装失败，可稍后手动: source ${PI_ENV_FILE} && pi install ${APP_DIR}/integrations/pi"
    return 0
  fi

  if verify_pi_agent_api "${token}"; then
    PI_SETUP_OK=1
    ensure_pi_env_autoload
    log "Pi Agent 配置完成"
  else
    warn "Pi 扩展已安装，但 Agent API 验证失败，请运行 ./scripts/check.sh"
  fi
}

print_summary() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')"
  echo ""
  echo "=========================================="
  echo " Sales CRM 部署成功"
  echo "=========================================="
  echo " 访问:    http://${ip}:${APP_PORT}/"
  echo " 健康:    http://${ip}:${APP_PORT}/health"
  echo " 账号:    admin / admin123  (登录后请在系统设置修改)"
  echo " 目录:    ${APP_DIR}"
  echo " 更新:    cd ${APP_DIR} && sudo ./scripts/deploy.sh"
  echo " 状态:    cd ${APP_DIR} && ./scripts/check.sh"
  if [[ "${PI_SETUP_OK}" == "1" && -n "${PI_ENV_FILE}" ]]; then
    echo " Pi:      source ${PI_ENV_FILE} && cd ${APP_DIR} && pi"
    echo " Pi 验证: curl -s -H \"Authorization: Bearer \$SALESCRM_TOKEN\" http://127.0.0.1:${APP_PORT}/api/agent/health"
  elif [[ "${SKIP_PI}" != "1" ]]; then
    echo " Pi:      安装未完成，见上方 WARNING 或 integrations/pi/README.md"
  fi
  echo " 日志:    cd ${APP_DIR} && docker compose logs -f"
  echo " 重启:    cd ${APP_DIR} && docker compose restart"
  echo " 停止:    cd ${APP_DIR} && docker compose down"
  echo "=========================================="
}

main() {
  log "Sales CRM 部署脚本"
  install_docker
  ensure_repo
  deploy_compose
  wait_healthy
  setup_pi_agent
  print_summary
}

main "$@"
