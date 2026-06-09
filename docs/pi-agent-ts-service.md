# Pi Agent TypeScript 微服务（方案 B）

Python CRM 主体保留数据库、认证、工具执行与线程持久化；Pi agent 决策循环与 LLM 流式在 Node/TypeScript 微服务中运行。

## 架构

```
Browser  →  POST /api/agent/chat/stream  →  salescrm (Python)
                                              ├─ 线程锁 / 持久化 / SSE 代理
                                              └─ 转发 →  pi-agent:8001/stream (TS)
                                                          ├─ decide_turn / agent loop
                                                          ├─ LLM streaming (DeepSeek)
                                                          └─ 工具 → POST /api/internal/pi/* (Python)
```

## 目录

| 路径 | 说明 |
|------|------|
| `services/pi-agent/` | Hono + SSE 微服务 |
| `app/pi_internal_routes.py` | Python 内部 API（prepare / tools / persist / 护栏） |

## 环境变量

| 变量 | 服务 | 说明 |
|------|------|------|
| `PI_AGENT_SERVICE_URL` | salescrm | 例如 `http://pi-agent:8001`；未设置则走 Python 内置 loop |
| `PI_INTERNAL_SECRET` | salescrm + pi-agent | 内部 API 共享密钥 |
| `CRM_INTERNAL_URL` | pi-agent | Python 基址，默认 `http://salescrm:8000` |

## 本地开发

```bash
# 终端 1：Python CRM
uvicorn app.main:app --reload --port 8000

# 终端 2：TS Pi agent
cd services/pi-agent
npm install
export CRM_INTERNAL_URL=http://127.0.0.1:8000
export PI_INTERNAL_SECRET=dev-secret
export PORT=8001
npm run dev

# 终端 1 环境
export PI_AGENT_SERVICE_URL=http://127.0.0.1:8001
export PI_INTERNAL_SECRET=dev-secret
```

## Docker Compose

```bash
PI_INTERNAL_SECRET=$(openssl rand -hex 24) docker compose up -d --build
```

`pi-agent` 在 `salescrm` 健康检查通过后启动。首次部署需重建镜像（新增 `services/pi-agent` Dockerfile）。

## 内部 API（仅 Docker 网络）

- `GET /api/internal/pi/llm-config`
- `POST /api/internal/pi/prepare`
- `POST /api/internal/pi/tools/run`（SSE）
- `POST /api/internal/pi/persist`
- `POST /api/internal/pi/tool-block`
- `POST /api/internal/pi/force-summary`
- `POST /api/internal/pi/recover-overflow`

均需请求头 `X-Internal-Secret`。

## 后台 Pi 任务

`background_jobs` 中的 `pi_agent` 在配置 `PI_AGENT_SERVICE_URL` 时同样走 `stream_pi_agent_events`（TS sidecar）；未配置时回退 Python `agent_chat_stream`。

## 上下文溢出恢复

TS sidecar 在 LLM 返回上下文过长错误时，会调用 `POST /api/internal/pi/recover-overflow`（压缩线程 + 重新 prepare）并自动重试一次。Python 回退路径在 `agent_chat_stream` 内有同等逻辑。

## 回退

取消 `PI_AGENT_SERVICE_URL` 或设为空，重启 `salescrm` 容器即可回到纯 Python Pi loop。
