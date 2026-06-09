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

工具协议以 Python `prepare` 返回的 `tools` / `tool_aliases` 为准。TS sidecar 会从这份 schema 动态生成严格工具名 registry，用于解析、恢复和校验模型 tool calls；未出现在 schema 中的工具名不会被当作合法工具，避免维护第二份硬编码工具名单。

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
# 注意：密钥须 ≥16 字符且不能是常见占位符，否则两侧都会拒绝（视为未配置）
export CRM_INTERNAL_URL=http://127.0.0.1:8000
export PI_INTERNAL_SECRET=dev-only-local-secret-001
export PORT=8001
npm run dev

# 终端 1 环境
export PI_AGENT_SERVICE_URL=http://127.0.0.1:8001
export PI_INTERNAL_SECRET=dev-only-local-secret-001
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

## 测试 harness

```bash
cd services/pi-agent
npm test          # build + 类型契约检查 + node --test 全量
npm run test:unit # 只跑测试（需先 build）
```

- `test/helpers.mjs`：`FakePython`（可脚本化的内部 API 假实现）+ `scriptedLlm`（按回合回放 LLM 流事件），对应 Python 侧的 `tests/fake_llm.py`。
- `test/agentLoop.test.mjs`：决策循环离线集成测试——工具回合、并行批次、护栏拦截、溢出恢复、心跳、取消、强制总结、轮次上限等。`agentChatStream` 暴露 `streamChatImpl` / `toolHeartbeatMs` 两个注入点供测试使用。
- 其余文件按模块对应：`streamParser` / `decisions` / `replyHeuristics` / `toolCalls` / `llmClient`（mock fetch）/ `pythonClient`（mock fetch）/ `guards`。
- `test/agentEvents.typecheck.ts`：SSE 事件契约的编译期校验。

## 取消

`/stream` 监听请求的 abort 信号：Python 代理断开（用户点停止/页面关闭）后，sidecar 在下一个检查点停止继续调用 LLM 与工具。

## 后台 Pi 任务

`background_jobs` 中的 `pi_agent` 在配置 `PI_AGENT_SERVICE_URL` 时同样走 `stream_pi_agent_events`（TS sidecar）；未配置时回退 Python `agent_chat_stream`。

## 上下文溢出恢复

TS sidecar 在 LLM 返回上下文过长错误时，会调用 `POST /api/internal/pi/recover-overflow`（压缩线程 + 重新 prepare）并自动重试一次。Python 回退路径在 `agent_chat_stream` 内有同等逻辑。

## 回退

取消 `PI_AGENT_SERVICE_URL` 或设为空，重启 `salescrm` 容器即可回到纯 Python Pi loop。
