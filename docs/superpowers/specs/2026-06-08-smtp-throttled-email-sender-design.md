# SMTP 限速发送队列 + Markdown 模板 — 设计

> 状态:已确认需求,待用户审阅 spec。日期:2026-06-08。

## 1. 背景与现状

- 当前外发是 `mailto:`(打开本机邮件客户端),无服务端发信。
- 邮件模板已存在(`email_templates`:name / subject / 纯文本 body + `{{变量}}`),CRUD 齐全;前端 `renderTemplateText(text, contact)` 做变量替换。
- 联系人已有 `email_sent` 字段与 `mark_contact_sent` 动作。
- 已有调度器(`app/scheduler.py`:轮询 loop + `scheduled_jobs` 表 + `interval_minutes`/`run_mode`/`cooldown_minutes`),但**仅用于 AI 线索发现**,不发邮件。其轮询/锁模式可复用。
- `lifespan`(`app/main.py`)启动时调用 `start_scheduler()`——发送 worker 在此并列启动。
- `settings_store.SECRET_KEYS` 对密钥做掩码/只写(如 `llm_api_key`)。

## 2. 目标与已确认决策

构建**服务端 SMTP 限速发送队列**:选一批联系人 + 模板入队,worker 按固定节奏匀速发出。

| 决策点 | 选定 |
|---|---|
| 发送形态 | 限速发送队列(drip outbox) |
| 节奏控制 | 可配**间隔** + **每日上限** + **活跃时段** |
| SMTP 范围 | 自动队列走 SMTP;单个手动发**保留 mailto** |
| 模板格式 | **Markdown** → 发送时渲染为 HTML + 纯文本(multipart) |
| 时区 | v1 用服务器本地时间 |

**非目标(YAGNI):** 打开/点击追踪、退订链接管理、A/B、富文本所见即所得编辑器、收件箱/回复同步、多发件身份轮换、SMTP 密码静态加密(沿用现有明文存储 + 掩码;单列为可选增强)。

## 3. 架构

**Outbox 表 + 专用限速 sender loop**(在 `lifespan` 与 scheduler 并列启动)。
拒绝的替代:复用 `scheduled_jobs`(为线索发现建模,塞收件人列表/逐封状态很别扭);事务型邮件 API(SES/SendGrid,送达更好但用户要 SMTP——作为送达率提醒列出)。

各单元职责清晰、可独立测试:
- **配置层**:`settings_store` 读写 SMTP/节奏设置。
- **模板渲染**:`render_email_markdown(md, contact)` → (subject, text, html)。
- **入队**:`POST /api/email/queue` 逐联系人渲染并插入 outbox。
- **限速门(纯函数)**:`within_active_hours`/`under_daily_cap`/`interval_elapsed` → 可单测。
- **发送器**:`email_sender.send_smtp(settings, msg)` + worker loop 调度。
- **UI**:SMTP 设置表单 + 模板预览 + 发送队列视图。

## 4. 数据模型

### 4.1 设置(settings_store 键)
- `smtp_host`, `smtp_port`, `smtp_security`(`none|ssl|starttls`), `smtp_username`, `smtp_password`(加入 `SECRET_KEYS`,掩码/只写/不回传), `from_name`, `from_email`。
- 节奏:`email_sender_enabled`(bool), `email_send_interval_minutes`(默认 5), `email_daily_cap`(默认 50), `email_active_start_hour`(默认 9), `email_active_end_hour`(默认 18)。

### 4.2 新表 `email_outbox`
| 列 | 说明 |
|---|---|
| `id` | PK |
| `user_id` | 所属用户 |
| `contact_id` | 收件联系人(可空,联系人被删后保留记录) |
| `template_id` | 来源模板(可空) |
| `to_email` | 收件地址 |
| `subject` | 渲染后主题 |
| `body_text` | 渲染后纯文本(Markdown 源 + 变量替换) |
| `body_html` | 渲染后 HTML |
| `status` | `queued`/`sending`/`sent`/`failed`/`cancelled` |
| `attempts` | 已尝试次数 |
| `last_error` | 最近错误 |
| `scheduled_at` | 入队时间(排序用) |
| `sent_at` | 实发时间 |
| `created_at` / `updated_at` | 时间戳 |

> 索引:`(user_id, status, scheduled_at)` 供 worker 取最旧 queued;`sent_at` 供日上限统计。

## 5. 组件细节

### 5.1 Markdown 模板
- `body` 仍是单一文本字段,**解释为 Markdown**(纯文本天然兼容,无需迁移)。
- 服务端渲染器 `app/email_render.py`:镜像前端 `renderMarkdown`(加粗/斜体/行内码/链接/列表/标题/段落),**不引入新依赖**;先做变量替换再渲染。
- `subject` 仅做变量替换(不渲染 Markdown)。
- 模板编辑器(系统设置)加**实时预览**(复用前端 `renderMarkdown`)。

### 5.2 入队
- 联系人**批量操作栏**新增「加入发送队列」按钮 → 弹窗:选模板 + 选项「跳过已发」「跳过已在队列」。
- `POST /api/email/queue { contact_ids[], template_id, skip_sent }`:
  - 跳过无邮箱 / 重复(同 user+email 已有 `queued`/`sending`)/(可选)`email_sent` 已发。
  - 逐联系人渲染 subject/body_text/body_html,插入 `queued` 行。
  - 返回 `{ queued: N, skipped: {...} }`。

### 5.3 发送器与 worker
- `app/email_sender.py`:
  - 纯函数门:`within_active_hours(now, start, end)`、`under_daily_cap(sent_today, cap)`、`interval_elapsed(last_sent_at, now, interval)`。
  - `build_message(settings, row)` → `email.message.EmailMessage`,multipart `text/plain`(body_text)+ `text/html`(body_html),`From: from_name <from_email>`。
  - `send_smtp(settings, msg)`:按 `smtp_security` 选 `SMTP`/`SMTP_SSL` + `starttls`,登录发送;`smtplib` 放 `asyncio.to_thread`。
- worker loop(lifespan 启动):每 ~60s 一 tick:
  1. 读设置;`enabled` 否则跳过。
  2. 门校验:活跃时段内 && 今日已发 < cap && 距上次发送 ≥ interval。
  3. 原子认领最旧 `queued` 行(`UPDATE ... SET status='sending' WHERE id=(SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`,防重发)。
  4. 发送 → 成功:`status='sent'`、`sent_at`、`mark_contact_sent`;失败:`attempts+1`,< 3 则回 `queued`(退避),否则 `failed` + `last_error`。
  5. **SMTP 连接/认证错误**(配置级):把认领行退回 `queued`、**暂停 sender**(`email_sender_enabled=false`)、记录错误,避免空烧整条队列。

### 5.4 Outbox UI
- 新「发送队列」视图:计数(排队/已发/失败/暂停态)、暂停/继续开关、取消某 `queued` 项、重试某 `failed` 项。
- 轮询刷新(复用 jobs bar 模式)。

### 5.5 API 一览
- `PUT /api/settings`(扩展,含 SMTP/节奏字段;密码掩码)。
- `POST /api/email/test { to, host, port, security, username, password, from_name, from_email }`:用**当前表单里的 SMTP 配置**测试(尚未保存也能测;`password` 留空则回退已保存值,以兼容掩码),执行 连接 → 认证 → 发一封测试信,**内联**返回成功或**具体错误**(无法连接 / 认证失败 / 发件被拒 / 超时)。
- `POST /api/email/queue { contact_ids, template_id, skip_sent }`。
- `GET /api/email/outbox?status=`:列队列。
- `POST /api/email/outbox/{id}/cancel` / `.../retry`。
- `POST /api/email/sender/toggle { enabled }`。

## 6. 数据流

选联系人 → 入队(逐封渲染、去重)→ worker 按门匀速认领 → SMTP multipart 发送 → `sent`/`failed` →(成功)`mark_contact_sent` → outbox 与联系人状态反映结果。

## 7. 错误处理

- 逐封失败:重试 ≤3 次(退避),终态 `failed` + `last_error`,**不阻塞**其余。
- 配置/认证错:暂停 sender + 报错,认领行退回 `queued`。
- 无效收件人/渲染失败:该行 `failed` 跳过。
- 联系人被删:outbox 行保留(`contact_id` 置空),不影响已渲染内容。

## 8. 安全

- `smtp_password` 进 `SECRET_KEYS`:掩码读取、只写、不回传(同现有 API key)。
- HTML 来自运营者自填模板(非外部输入),渲染器只产出受控标签;不注入收件人可控的原始 HTML。
- 说明:现有密钥为明文存 DB + 掩码读取;本设计与之一致。**静态加密**列为可选后续增强,不在本期。

## 9. 送达率提醒(用户基建,非本期代码)

裸 SMTP 冷发件是否进垃圾箱,主要取决于 SMTP 服务商与**发件域的 SPF/DKIM/DMARC**。限速 + 活跃时段 + 日上限缓解"量"的风控,但域认证是前提。文档在 UI 给一句提示链接即可。

## 10. 测试策略(fake/monkeypatch,不走真实网络)

- 限速门纯函数:活跃时段边界、日上限、间隔。
- 入队:渲染正确、跳过无邮箱/重复/已发、计数。
- Markdown 渲染:加粗/链接/列表/段落、变量替换、纯文本与 HTML 双产出、纯文本模板向后兼容。
- 发送:`send_smtp` 用假 SMTP 对象断言 multipart 结构 + 登录路径(ssl/starttls/none);成功→`sent`+`mark_contact_sent`,失败→重试/`failed`,认证错→暂停。
- worker tick:认领唯一行、门不满足时不发。

## 11. 分期(各自 commit + 测试)

- **P1**:SMTP/节奏设置(settings + 表单 + 掩码)、`email_render` + 模板预览、`email_sender.send_smtp`、`POST /api/email/test`。
- **P2**:`email_outbox` 表 + 入队 API + 联系人批量「加入发送队列」+ worker loop(限速/日上限/活跃时段)+ 状态机/重试/暂停。
- **P3**:发送队列 UI(暂停/继续/重试/取消)+ i18n(中/英)+ 打磨;CI(ruff format + 前端 build artifacts)收尾。
