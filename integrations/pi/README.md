# Sales CRM × Pi Coding Agent

在同一台 VPS 上让 [Pi Coding Agent](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) 把爬取/脚本得到的线索导入 Sales CRM。

## 1. CRM 侧

运行 `./scripts/deploy.sh` 会自动：

- 从容器读取 Agent API Token 并写入 `${APP_DIR}/.pi-env`
- 安装 Node.js 20、Pi CLI、Sales CRM 扩展包
- 在 `~/.bashrc` 加入 `source .pi-env`（仅首次）

手动重新生成 Token：Web UI **系统设置 → 自动化 → Pi Agent API → 重新生成**，然后重新部署或更新 `.pi-env`。

验证：

```bash
source /opt/salescrm/.pi-env
curl -s -H "Authorization: Bearer $SALESCRM_TOKEN" \
  http://127.0.0.1:8000/api/agent/health
```

跳过 Pi 安装：`SKIP_PI=1 ./scripts/deploy.sh`

## 2. 手动安装（可选）

若自动步骤失败，可手动执行：

需要 Node.js 18+：

```bash
npm install -g @mariozechner/pi-coding-agent
```

配置环境变量（写入 `~/.bashrc`）：

```bash
export SALESCRM_URL=http://127.0.0.1:8000
export SALESCRM_TOKEN=<你的-token>
```

## 3. 安装本扩展包

在 VPS 上（仓库已在 `/opt/salescrm`）：

```bash
pi install /opt/salescrm/integrations/pi
```

或从 GitHub：

```bash
pi install git:https://github.com/TangLiChun/salescrm.git#main:integrations/pi
```

（若 `git:` 子路径不可用，请用本地路径安装。）

## 4. 使用

启动 Pi：

```bash
cd /opt/salescrm
pi
```

示例对话：

- 「检查 Sales CRM 是否连通」→ `salescrm_health`
- 「用 Playwright 抓这些 ASN 的 abuse 邮箱，导入 CRM」→ 脚本 + `salescrm_import_leads`
- 「在 CRM 里搜一下是否已有 cloudflare.com 的联系人」→ `salescrm_list_contacts`

## Agent API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agent/health` | 探活 + schema |
| GET | `/api/agent/contacts?q=` | 搜索联系人 |
| POST | `/api/agent/leads/import` | `{ "rows": [...], "source": "pi-agent" }` |
| POST | `/api/agent/leads/discover` | `{ "query": "...", "min_score": 60, "auto_import": false }` |

所有请求需头：`Authorization: Bearer <token>`

## 文件结构

```
integrations/pi/
├── package.json          # pi-package 清单
├── extensions/salescrm.ts
├── skills/salescrm/SKILL.md
└── README.md
```
