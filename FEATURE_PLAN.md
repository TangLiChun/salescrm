# Sales CRM 功能计划

> Loop 每 1 分钟推进下一项。状态：`pending` | `in_progress` | `done`

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 1 | 修改当前用户密码 | done | POST /api/me/password + 系统设置 UI |
| 2 | 联系人跟进状态 | in_progress | new/contacted/replied/invalid/interested |
| 3 | 邮件模板 + 变量发信 | pending | 模板 CRUD + mailto 预填 |
| 4 | AI 线索导入预览勾选 | pending | 导入前可选行 |
| 5 | 联系人备注时间线 | pending | contact_notes 表 |
| 6 | 健康检查 /health | pending | 探活用 |
| 7 | SQLite WAL 模式 | pending | 并发写入优化 |
| 8 | 定时任务运行历史 | pending | job_runs 表 + UI |
| 9 | 黑名单/白名单 | pending | 导入过滤 |
| 10 | 统计仪表盘 | pending | 首页概览 |

## Loop 指令

每次 tick 读取本文件，将第一个 `pending` 或 `in_progress` 项标为 `in_progress` 并完成实现，完成后标 `done` 并 git commit（用户未要求则不 push）。
