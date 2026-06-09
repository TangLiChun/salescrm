# Sales CRM 功能计划

> Loop 每 1 分钟推进下一项。状态：`pending` | `in_progress` | `done`

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 1 | 修改当前用户密码 | done | POST /api/me/password + 系统设置 UI |
| 2 | 联系人跟进状态 | done | new/contacted/replied/invalid/interested |
| 3 | 邮件模板 + 变量发信 | done | 模板 CRUD + mailto 预填 |
| 4 | AI 线索导入预览勾选 | done | 导入前可选行 |
| 5 | 联系人备注时间线 | done | contact_notes 表 |
| 6 | 健康检查 /health | done | 探活用 |
| 7 | SQLite WAL 模式 | done | 并发写入优化 |
| 8 | 定时任务运行历史 | done | job_runs 表 + UI |
| 9 | 黑名单/白名单 | done | 导入过滤 |
| 10 | 统计仪表盘 | done | 首页概览 |

## 第二阶段

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 11 | 联系人搜索 | done | 按组织/姓名/邮箱/备注搜索 |
| 12 | 联系人导出 CSV | done | 按当前筛选导出 |
| 13 | 定时任务立即运行 | done | POST /api/schedules/{id}/run |
| 14 | 发邮件后标记已发 | done | mailto 后可选标记 |

## 第三阶段

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 15 | 联系人编辑 | done | PATCH 组织/姓名/Role/备注 |
| 16 | 批量操作 | done | 批量改状态、标记已发、删除 |
| 17 | 联系人分页 | done | page/page_size，默认 50 条/页 |
| 18 | 数据库备份 | done | GET /api/backup 下载 .db |

## 第四阶段（规划中）

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 19 | 更多搜索渠道 | pending | 在 app/sources 下新增渠道（如 RIPE/APNIC RDAP、行业目录） |
| 20 | 外部 Agent API | done | `/api/agent/*` + 设置页 Token（无捆绑 CLI） |

## Loop 指令

每次 tick 读取本文件，将第一个 `pending` 或 `in_progress` 项标为 `in_progress` 并完成实现，完成后标 `done` 并 git commit（用户未要求则不 push）。
