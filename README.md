# Sales CRM

面向网络运营商（ASN / Peering / 主机）线索获取与外联的轻量 CRM：ASN RDAP 查询、AI 线索发现、联系人管理、邮件模板与限速发信，内置 **Pi 助手**（应用内 AI 对话 agent），并支持外部编码 agent（[DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix)）通过 Agent API 驱动线索导入。

- 后端：FastAPI（Python 3.12）+ PostgreSQL
- 前端：原生 TypeScript（`tsc` 编译为静态资源，无运行时框架）
- 部署：Docker Compose（Linux VPS 一键脚本；macOS 用 Docker Desktop）

---

## 架构

`docker compose` 启动三个服务：

| 服务 | 镜像 / 技术 | 端口 | 作用 |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 5432（内部） | 数据库 |
| `salescrm` | FastAPI · Python 3.12 · uvicorn | **8000**（对外） | Web 应用 + REST API + `/api/agent/*` |
| `pi-agent` | Node 20 · Hono | 8001（内部） | 应用内「Pi 助手」的编码 agent 后端，经 `PI_INTERNAL_SECRET` 内部鉴权 |

其它：

- **前端**：`frontend/src/**.ts` 由 `tsc` 编译进 `app/static/js`（产物已提交并被 CI 校验）。
- **外部 agent 集成**：`integrations/reasonix/` —— 一个零依赖的 `salescrm` CLI + Reasonix skill，让 DeepSeek-Reasonix 通过 `/api/agent/*`（Bearer Token）导入/发现线索。详见 [`integrations/reasonix/README.md`](integrations/reasonix/README.md)。

> 「Pi」在本项目有两层含义，互不相关：①应用内的 **Pi 助手**（网页对话，由 `pi-agent` sidecar 支撑）；②**外部 Agent API**（设置 → 自动化），供 Reasonix 等外部 agent 调用。

---

## 快速开始（Docker Compose · Linux/macOS 通用）

前置：已安装 **Docker** 与 **Docker Compose v2**（macOS 用 Docker Desktop，见下节）。

```bash
git clone https://github.com/TangLiChun/salescrm.git
cd salescrm
cp .env.example .env          # 本地默认值即可直接用
docker compose up -d --build  # 拉起 postgres + salescrm + pi-agent
```

打开 <http://localhost:8000/>，默认账号 **admin / admin123**（登录后请到「系统设置」修改密码）。

常用命令：

```bash
docker compose ps                 # 查看状态/健康
docker compose logs -f salescrm   # 跟日志
docker compose restart salescrm   # 重启应用（改了 app/ 代码后，因挂载只需重启）
docker compose down               # 停止（数据保留在 salescrm_pgdata 卷）
```

> 前端产物已打进镜像，Docker 方式**无需**在宿主机装 Node。

---

## macOS 部署流程

`scripts/deploy.sh` 面向 **Linux VPS**（用到 `sudo`、`hostname -I`、`/opt` 等），**不要**在 macOS 上直接跑。macOS 用下面两种方式之一。

### 方式 A —— Docker Desktop（推荐，完整三服务栈）

1. 安装并启动 Docker Desktop：

   ```bash
   brew install --cask docker
   open -a Docker            # 首次启动并等待 Docker 就绪（菜单栏鲸鱼图标变绿）
   ```

2. 克隆 + 配置 + 启动（与上面「快速开始」一致）：

   ```bash
   git clone https://github.com/TangLiChun/salescrm.git
   cd salescrm
   cp .env.example .env
   docker compose up -d --build
   ```

3. 等三个容器健康后访问 <http://localhost:8000/>（admin / admin123）：

   ```bash
   docker compose ps     # STATUS 列应为 healthy
   ```

4. （可选）接入 Reasonix —— deploy.sh 的自动步骤是 Linux 专用的，macOS 手动三步：

   ```bash
   # ① 在 Web UI：设置 → 自动化 → 外部 Agent API → 重新生成 → 复制 Token
   export SALESCRM_URL=http://localhost:8000
   export SALESCRM_TOKEN=<粘贴 Token>            # 建议写进 ~/.zshrc
   # ② 把 CLI 放上 PATH（任选其一）
   ln -sf "$PWD/integrations/reasonix/bin/salescrm" /usr/local/bin/salescrm
   # ③ 安装 Reasonix 并注册 skill（见 integrations/reasonix/README.md）
   npm i -g reasonix
   salescrm health        # {"ok": true, ...} 即打通
   ```

### 方式 B —— 原生本地开发（仅 app + 数据库，更轻）

适合改代码/跑测试；注意此方式默认**不含**「Pi 助手」sidecar（见末尾说明）。

1. 安装并启动 PostgreSQL，创建与默认配置匹配的角色与库：

   ```bash
   brew install postgresql@16
   brew services start postgresql@16
   createuser -s salescrm 2>/dev/null || true
   psql -d postgres -c "ALTER USER salescrm WITH PASSWORD 'salescrm';"
   createdb -O salescrm salescrm
   ```

   （或自建库后用 `export DATABASE_URL=postgresql://用户:密码@localhost:5432/库名` 覆盖默认值。）

2. Python 依赖：

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt   # 含运行时依赖 + 测试工具
   ```

3. 前端产物已提交；若改了 `frontend/src/**.ts` 才需重建：

   ```bash
   npm install
   npm run build:frontend
   ```

4. 启动应用：

   ```bash
   .venv/bin/uvicorn app.main:app --reload --port 8000
   ```

   访问 <http://localhost:8000/>（admin / admin123）。

> **Pi 助手**需要 `pi-agent` sidecar（Node 20）。最省事是用方式 A 的 Docker 跑起 sidecar；或单独运行：`cd services/pi-agent && npm install && npm run build && CRM_INTERNAL_URL=http://localhost:8000 PI_INTERNAL_SECRET=change-me npm start`（同时给应用设 `PI_AGENT_SERVICE_URL=http://localhost:8001` 与相同的 `PI_INTERNAL_SECRET`）。其余功能（ASN 查询、线索、联系人、邮件）在方式 B 下均可用。

---

## 配置

复制 `.env.example` 为 `.env`。Compose 以 `${VAR:-默认值}` 读取，开箱即用，常见可调项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_PORT` | `8000` | 对外端口 |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | `salescrm` | 数据库账号/密码/库名 |
| `DATABASE_URL` | （由上面拼出） | 直接指定完整连接串则忽略上面几项 |
| `PI_INTERNAL_SECRET` | `change-me-in-production` | 应用 ↔ pi-agent 内部鉴权，**生产务必改** |

应用内运行时配置（LLM Key、搜索渠道、SMTP、外部 Agent Token 等）在 **Web UI → 系统设置** 里维护，存于数据库。

---

## 开发

```bash
./scripts/test.sh            # ruff check + ruff format --check + pytest（自动用 .venv）
./scripts/test.sh --live     # 额外跑可选的真实 DeepSeek 冒烟 / Pi harness
npm run check:frontend       # 前端 typecheck + build + node --check（CI 会校验产物 diff）
```

> 改了 `frontend/src/**.ts` 后必须 `npm run build:frontend` 并提交 `app/static/js`、`app/static/i18n.js` 等产物，否则 CI 的产物 diff 校验会失败。

---

## 故障排查

### 容器起不来 / 状态 unhealthy

```bash
docker compose ps                  # 查看各服务状态与健康
docker compose logs salescrm       # 应用日志（看启动报错）
docker compose logs postgres       # 数据库日志
```

`salescrm` 依赖 `postgres` 健康后才启动（`depends_on: condition: service_healthy`），若 postgres 一直 starting/unhealthy，先排查数据库日志。

### 端口 8000 被占用

在 `.env` 中修改 `APP_PORT`，然后重启：

```bash
# .env
APP_PORT=8080
```

```bash
docker compose up -d
```

浏览器改用 <http://localhost:8080/>。

### 原生方式报 `role "salescrm" does not exist` / 连不上数据库

默认连接串（`app/db.py`）：`postgresql://salescrm:salescrm@localhost:5432/salescrm`。

创建角色与库（PostgreSQL 16）：

```bash
createuser -s salescrm
psql -d postgres -c "ALTER USER salescrm WITH PASSWORD 'salescrm';"
createdb -O salescrm salescrm
```

或用环境变量指向已有数据库：

```bash
export DATABASE_URL=postgresql://用户:密码@localhost:5432/库名
```

### `/health` 返回 `"schema": false`

表示数据库表尚未建好。应用首次启动会自动执行 `init_db()`；请确认数据库可连接，并检查容器日志无报错。若手动跑原生方式，确保 `DATABASE_URL` 指向正确且可访问的数据库后重新启动应用。

### Pi 助手不可用

Pi 助手依赖 `pi-agent` sidecar（Node 20，端口 8001）。Docker Compose 方式会自动启动该服务；**原生方式默认不含 sidecar**，需单独运行（参见上方「方式 B」末尾说明）。其余功能（ASN 查询、联系人、邮件）不受影响。

### Reasonix `salescrm health` 报 token 未设置 / 401

```bash
export SALESCRM_TOKEN=<Token>      # 确保已在当前 shell 导出
salescrm health
```

Token 来自 Web UI：**设置 → 自动化 → 外部 Agent API → 重新生成**。重新生成后旧 Token **立即失效**，需重新导出。建议写入 `~/.zshrc`（或 `~/.bashrc`）避免每次手动导出。

### 改了前端 TS 但页面没变

前端产物需手动重建：

```bash
npm run build:frontend              # 重新编译 frontend/src/*.ts → app/static/js
```

Docker 方式还需重启容器使新产物生效：

```bash
docker compose restart salescrm
```

---

## 运维速查（停止 / 备份 / 卸载）

```bash
# 停止（数据保留在 salescrm_pgdata 卷）
docker compose down

# 备份数据库
docker compose exec postgres pg_dump -U salescrm salescrm > backup.sql

# 恢复数据库
cat backup.sql | docker compose exec -T postgres psql -U salescrm salescrm

# 彻底卸载（含数据）—— 会删除 salescrm_pgdata 卷，数据丢失，不可恢复
docker compose down -v
```

---

## 部署到 Linux VPS（一键）

在服务器上：

```bash
git clone https://github.com/TangLiChun/salescrm.git /opt/salescrm
cd /opt/salescrm && sudo ./scripts/deploy.sh
```

更新：`cd /opt/salescrm && sudo ./scripts/deploy.sh`（改代码可加 `DEPLOY_FAST=1`）。

`deploy.sh` 会构建并 `docker compose up`、做健康检查与 API 冒烟，并（除非 `SKIP_REASONIX=1`）自动安装 Reasonix、写 `.reasonix-env`、软链 `salescrm` CLI、注册 skill。常用开关见脚本头部注释（`APP_PORT` / `DEPLOY_FAST` / `SKIP_REASONIX` / `FORCE_REBUILD` 等）。

部署后巡检：`./scripts/check.sh`。

---

## 目录结构

```
app/                     FastAPI 应用（路由、数据库、Pi 助手、agent API、settings…）
frontend/src/            前端 TypeScript 源码（编译进 app/static/js）
services/pi-agent/       Pi 助手编码 agent sidecar（Node/Hono）
integrations/reasonix/   外部 agent 集成：salescrm CLI + Reasonix skill + 配置示例
scripts/                 deploy.sh（VPS 一键）、check.sh（巡检）、test.sh（本地测试）…
docs/superpowers/        设计 spec 与实现计划
tests/                   pytest 测试
docker-compose.yml       三服务编排（postgres / salescrm / pi-agent）
Dockerfile               salescrm 应用镜像
```

---

## 访问与默认值

- 应用：<http://localhost:8000/>
- 健康检查：`GET /health`（返回 `{ok, db, schema}`）
- 默认账号：`admin` / `admin123` —— **首次登录后请立即修改**。
