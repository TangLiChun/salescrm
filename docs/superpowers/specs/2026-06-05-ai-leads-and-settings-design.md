# AI 线索发现完善 + 系统设置人性化 — 设计

日期：2026-06-05
范围：前端为主（`app/static/index.html` · `app/static/app.js` · `app/static/style.css`），不改后端 API
与数据模型；仅删除前端死代码、在 `FEATURE_PLAN.md` 记录下一阶段事项。

## 1. 背景与目标

当前两个界面有明确的体验缺口：

- **AI 线索发现**：流程端到端可用（理解需求 → PeeringDB + 搜索引擎 + ARIN RDAP → LLM 提取/评分
  → 导入），但实时反馈很薄——多个 `source_result` 事件被压成一行不断被覆盖的进度文字；没有
  持久的逐渠道结果面板；`networks` 事件在前端有处理分支但后端从不发送（死代码）；没有取消/重试；
  线索行无法查看完整信息；空态/错误态只弹一个 `alert`。
- **系统设置**：单个 760px 表单把 8 个 `<fieldset>`（密码 / 账号 / LLM / 搜索引擎 / 导入过滤 /
  定时任务 / 邮件模板 / 数据备份）堆在一列，难以扫读，初始化类危险项与日常项混在一起。

目标：让线索发现过程"看得见、可控、可追溯、出错有引导"，让系统设置分类清晰、按需展示、误改风险低。

非目标（本次明确不做，记入 `FEATURE_PLAN.md` 下一阶段）：新增搜索渠道、集成外部 agent（"pi agent"）、
后端评分/提取算法改动。

## 2. Part A — 系统设置：左侧分类导航 + 右侧内容

### 2.1 结构

将 `#settings-view` 改造成两栏外壳：

- **左侧分类轨（rail）**：垂直的分类按钮列表，每个按钮含分类名 + 可选状态点。
- **右侧内容区**：仅渲染当前激活分类对应的面板，其余面板用 CSS（`hidden`）隐藏但仍存在于 DOM 中。

**关键约束：保留单一 `<form id="settings-form">` 包裹全部面板。** 因为所有输入元素始终在 DOM 中（只是
视觉隐藏），现有的 `saveSettings()` / `loadSettingsForm()` 收集逻辑无需改动即可继续工作。

### 2.2 分类与归组（8 fieldset → 6 分类）

| 分类 key | 标题 | 包含原 fieldset | 状态点 | 全局保存按钮 |
|---|---|---|---|---|
| `account` | 账号安全 | 修改登录密码 + 登录账号（仅首次初始化） | 无 | 显示 |
| `ai` | AI 与搜索 | LLM（API Key/Base URL/Model）+ 搜索引擎 API | ● 绿=LLM 已配置 | 显示 |
| `import` | 线索导入 | 导入过滤（黑名单/白名单） | 无 | 显示 |
| `automation` | 自动化 | 定时任务（启用开关 + 检查间隔） | ● 绿=已启用 | 显示 |
| `templates` | 邮件模板 | 邮件模板 CRUD | 无 | 隐藏（有自己的「保存模板」） |
| `backup` | 数据备份 | 数据备份下载 | 无 | 隐藏（有自己的「下载」） |

### 2.3 人性化处理

1. **分类描述**：每个面板顶部一句白话说明用途。示例：
   - 账号安全：「管理你的登录凭证。默认账号/密码仅在系统首次初始化时生效，已登录后请用上方修改密码。」
   - AI 与搜索：「AI 线索发现依赖 LLM；搜索引擎 Key 为可选增强，留空时默认使用 DuckDuckGo。」
   - 线索导入：「控制哪些邮箱可以被导入。白名单非空时仅导入匹配项；黑名单始终排除。」
   - 自动化：「让服务在后台按间隔自动跑线索发现并导入。」
2. **状态点**：分类轨上，AI 与搜索、自动化 右侧显示一个 5px 状态点（绿=已配置/已启用，灰=未配置/未启用），
   数据由 `loadSettingsForm()` 读到的配置态驱动；切换/保存后刷新。状态点遵循设计系统"状态不只靠颜色"——
   附 `title`/`aria-label` 文本（如「LLM 已配置」）。
3. **危险/初始化项收纳**：账号安全分类内，把「默认用户名 / 默认密码 / Session Secret」放进一个默认收起的
   `<details>`「高级：首次初始化设置」，与日常的「修改登录密码」分开，降低误改。
4. **保存按钮上下文化**：全局「保存设置」放在右侧内容区底部的 sticky footer；仅当激活分类属于
   {account, ai, import, automation} 时显示。templates/backup 分类隐藏全局保存（各自有内联动作）。
   `#settings-status` 随之放在 footer。
5. **移动端**：分类轨在窄屏折叠为顶部横向滚动条（与主标签 `.tabs` 一致的横滚策略，不换行）。

### 2.4 交互/状态

- 默认激活第一个分类（`account`）。
- 点击分类轨按钮：切换激活态（设计系统的"抬起的键"视觉）、显示对应面板、按 2.3.4 决定 footer 可见性。
- 切换分类不丢失未保存的输入（DOM 始终保留）。
- 键盘可达：分类按钮可 Tab 聚焦，可见 petrol 焦点环。

## 3. Part B — AI 线索发现：4 项改进

### 3.1 B1 实时渠道进度面板

把单行覆盖式进度替换为持久的**渠道读数面板**（仪表条风格，沿用 readout/hairline 语言）。每个渠道一行：
渠道名（sans）· 状态 · 计数（mono tabular）· 简短预览（mono，截断）。

固定渠道行（按发现流程顺序）及其驱动事件：

| 渠道行 | 显示名 | 由哪些流事件驱动 |
|---|---|---|
| `peeringdb` | PeeringDB | `source_result.source=="peeringdb"` |
| `web_search` | 搜索引擎 | `source_result.source=="web_search"` |
| `web_regex` | 网页解析 | `source_result.source=="web_regex"` |
| `llm_extract` | LLM 提取 | `source_result.source=="llm_extract"` |
| `arin` | ARIN RDAP | `progress`（index/total）+ `asn_result`（累计候选数） |
| `scoring` | LLM 评分 | 含"评估""评分"的 `status` 文本 → 进行中；`done` → 完成 |

状态机：`待命(idle)` → `进行中(active)` → `完成(done)` / `失败(failed，带原因)`。
- 面板在点击「开始」时初始化全部行为 `待命`。
- 收到对应事件时把该行置 `进行中`/`完成` 并填计数与预览。
- ARIN 行保留细 `<progress>` 条展示 `index/total`，并随 `asn_result` 累计候选数。
- 渠道部分失败（如 `extract_leads_from_web` 抛错对应的 `status` 文案"网页线索提取部分失败"）→ 对应行
  标记 `失败` 并显示原因，其余渠道继续。
- 状态用图标/文字+颜色双编码（✓/◐/·/×），不只靠颜色。

实现要点：用一个 `channelState` 对象保存各行状态；新增 `renderChannelPanel()` 在每次事件后重渲染。
保留旧的简短 `aiProgressText` 作为"当前动作"副标题亦可，但主反馈是面板。

死代码清理：删除 `payload.type === "networks"` 分支（后端不发送）。

### 3.2 B2 取消 / 重试

- 用 `AbortController` 包裹 `/api/leads/discover/stream` 的 `fetch`。
- 发现进行中：「AI 开始找线索」按钮切换为「取消」（secondary/clay 文案，非 primary）。点击 → `abort()`
  → 关闭流 → UI 复位到 idle（面板保留已得结果，进度标记"已取消"）。
- `AbortError` 不弹错误 alert，按"已取消"处理。
- 失败 或 结果为空 的 `done`/`error`：在结果区显示「重试」按钮，点击用同一 query 重新 `runLeadDiscovery()`。
- 取消/中断后正确恢复 `discoverBtn.disabled = !llmConfigured`。

后端：客户端 abort 即断开连接，FastAPI `StreamingResponse` 会停止迭代异步生成器；后台 `to_thread`
任务可能跑完但无副作用（不自动导入除非勾选）。本次不改后端。

### 3.3 B3 线索详情

- 每条线索行新增「详情」文字按钮（petrol-ink，行内动作）。
- 点击打开**模态框**，复用现有 `.contact-notes-modal` + `.contact-notes-backdrop` 模式（Overlay Pop 阴影）。
- 模态内容（机器字段 mono、人写字段 sans）：组织 · 邮箱（mailto 链接）· ASN · 全部 roles（role chip）·
  来源 + source_detail · network_name · matched_keyword · AI 评分（score badge）· 完整 AI 理由。
- 模态内提供一个"导入此线索"勾选/开关，与该行的 `_selected` 双向同步；关闭后列表勾选态一致。
- 关闭：点背景、关闭按钮、Esc。

### 3.4 B4 空 / 错误状态

结果区（`#ai-leads-body` 空行 + 必要时一个状态卡）按场景给出引导：

1. **LLM 未配置**：显示引导卡 +「去系统设置 → AI 与搜索」按钮，点击 `switchView("settings")` 并激活
   `ai` 分类。`discoverBtn` 保持禁用并说明原因（沿用 `llm-status.warn`）。
2. **无结果**（done 且 leads 为空）：友好说明 + 「重试」+ 具体建议文案（如"试试降低最低匹配分，或用更宽泛的
   关键词描述目标"）。
3. **渠道部分失败**：见 3.1，面板内标红，不阻断整体。
4. **流中断/请求失败**：结果区错误状态 + 「重试」，替代当前的裸 `alert`（AbortError 除外，见 B2）。

## 4. 受影响文件

- `app/static/index.html`：重构 `#settings-view`（两栏外壳 + 6 分类面板 + `<details>` 高级区 + sticky
  footer）；为 AI 线索区加渠道面板容器、取消/重试按钮、线索详情模态。
- `app/static/app.js`：设置分类切换 + 状态点 + footer 可见性逻辑；`channelState` + `renderChannelPanel()`；
  `AbortController` 取消/重试；线索详情模态开关与同步；空/错误态渲染；删除 `networks` 死分支。
- `app/static/style.css`：设置两栏布局（rail + content + 移动端横滚）、状态点、sticky footer；渠道面板
  （仪表条/hairline）、线索详情模态（复用 notes 模态变量）、空/错误状态卡。
- `FEATURE_PLAN.md`：新增下一阶段条目——更多搜索渠道 / 外部 agent（"pi agent"）集成（`pending`）。

## 5. 验证

- 设置：六个分类可切换、输入不丢失、保存仍写入全部表单字段（账号/AI/导入/自动化）、状态点随配置变化、
  templates/backup 不显示全局保存、移动端轨横滚、键盘可达且焦点环可见。
- 线索发现：跑一次发现，渠道面板逐行点亮且计数/预览正确；进行中可取消并复位；无结果/失败出现重试；
  LLM 未配置出现去设置引导并能跳转激活 AI 分类；点详情弹模态、字段完整、导入勾选与列表同步；
  `networks` 死代码已移除。
- 设计系统一致性：唯一 petrol 强调色、机器数据 mono tabular、hairline 优先、状态色+文字/图标双编码、
  无纯白/纯黑、模态用 Overlay Pop。

## 6. 设计系统约束（摘自 DESIGN.md）

- 一个强调色（petrol）只用于可操作/激活/焦点；状态色低饱和且语义化（moss/ochre/clay）。
- 机器标识符（ASN/邮箱/handle/计数/评分/时间）一律 mono + tabular-nums；人写文本用 sans。
- 边框优先于阴影；仅两种阴影（Resting Lift / 模态 Overlay Pop）。
- 状态不只靠颜色：配状态点+文字或图标。
- 不引入第二强调色、不用纯白浮卡、不做 hero-metric 仪表盘。
