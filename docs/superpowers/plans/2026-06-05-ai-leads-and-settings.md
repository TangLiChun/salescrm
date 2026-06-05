# AI 线索发现完善 + 系统设置人性化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AI 线索发现"看得见、可控、可追溯、出错有引导"，并把系统设置从单列长表单改造成左侧分类导航 + 右侧内容的人性化布局。

**Architecture:** 纯前端改动（`app/static/index.html` · `app/static/app.js` · `app/static/style.css`），不动后端 API、数据模型或评分/提取逻辑。设置改造保留单一 `<form>`（仅视觉分栏，DOM 始终完整）以复用现有保存逻辑。线索发现新增渠道状态面板、AbortController 取消/重试、详情模态、空/错误引导态，并修复 AI 行勾选未联动的既有缺口。

**Tech Stack:** 原生 HTML/CSS/JS（无框架、无构建步骤），FastAPI 静态托管。无 JS 测试框架——**验证方式为 `node --check` 语法校验 + 运行应用的可视化验证**（用 `run`/`verify` 技能或本地 `uvicorn app.main:app`）。后端无改动，故无需 Python 测试。

**设计系统约束（DESIGN.md）：** 唯一 petrol 强调色；机器数据 mono+tabular-nums，人写文本 sans；边框优先于阴影（仅 Resting Lift 与模态 Overlay Pop）；状态色低饱和且语义化（moss/ochre/clay），状态不只靠颜色（配点/图标/文字）；不用纯白/纯黑、不引入第二强调色。CSS 变量沿用现有 `--petrol` `--surface` `--surface-sunk` `--line` `--ink` `--ink-soft` `--ink-muted` `--positive` `--caution` `--danger` `--space-*` `--r-*` `--text-*`。

---

## 文件结构

| 文件 | 责任 | 本计划改动 |
|---|---|---|
| `app/static/index.html` | 页面结构 | 重构 `#settings-view`；为 AI 区加渠道面板、取消/重试按钮、线索详情模态 |
| `app/static/app.js` | 行为 | 设置分类切换/状态点/footer；channelState + 渲染；AbortController；详情模态 + AI 勾选联动；空错态；删 `networks` 死分支 |
| `app/static/style.css` | 样式 | 设置两栏/状态点/footer/移动横滚；渠道面板；详情模态；空错态卡 |
| `FEATURE_PLAN.md` | 路线图 | 记录下一阶段"更多渠道 / 外部 agent"为 `pending` |

> 既有缺口（实现中处理）：`.row-import-check` 复选框没有任何 `change` 处理器，取消勾选不会把 `_selected` 置 false。本计划在 Task 7 为 AI 线索行补上联动（详情模态需要可用的勾选）。lookup 表存在同样缺口，但不在本次范围内，仅记录。

---

## Part A — 系统设置

### Task 1: 重构系统设置为左侧分类轨 + 右侧内容外壳

**Files:**
- Modify: `app/static/index.html`（`#settings-view`，当前约 228-361 行）

- [ ] **Step 1: 用两栏外壳替换 `#settings-view` 的内部结构**

把 `app/static/index.html` 中从 `<section id="settings-view" ...>` 开始到该 `</section>` 结束的整段，替换为下面结构。它保留**全部原有输入元素的 id 不变**（保证 JS 复用），只是按分类分组进 `.settings-pane`，并新增分类轨、描述、`<details>` 高级区与 sticky footer。

```html
    <section id="settings-view" class="panel settings-view hidden">
      <div class="results-header">
        <div>
          <h2>系统设置</h2>
          <p class="stats">配置保存在数据库中，无需 .env 文件</p>
        </div>
      </div>

      <div class="settings-shell">
        <nav class="settings-rail" id="settings-rail" aria-label="设置分类">
          <button type="button" class="settings-rail-item active" data-settings-cat="account">账号安全</button>
          <button type="button" class="settings-rail-item" data-settings-cat="ai">
            AI 与搜索 <span class="rail-dot" id="rail-dot-ai" title="LLM 未配置"></span>
          </button>
          <button type="button" class="settings-rail-item" data-settings-cat="import">线索导入</button>
          <button type="button" class="settings-rail-item" data-settings-cat="automation">
            自动化 <span class="rail-dot" id="rail-dot-automation" title="定时任务未启用"></span>
          </button>
          <button type="button" class="settings-rail-item" data-settings-cat="templates">邮件模板</button>
          <button type="button" class="settings-rail-item" data-settings-cat="backup">数据备份</button>
        </nav>

        <div class="settings-content">
          <form id="settings-form" class="settings-form">
            <!-- 账号安全 -->
            <div class="settings-pane" data-settings-pane="account">
              <p class="settings-desc">管理你的登录凭证。默认账号/密码仅在系统首次初始化时生效，已登录后请用下方修改密码。</p>
              <fieldset>
                <legend>修改登录密码</legend>
                <label class="field"><span>当前密码</span>
                  <input id="pwd-current" type="password" autocomplete="current-password"></label>
                <label class="field"><span>新密码</span>
                  <input id="pwd-new" type="password" autocomplete="new-password" minlength="6"></label>
                <label class="field"><span>确认新密码</span>
                  <input id="pwd-confirm" type="password" autocomplete="new-password" minlength="6"></label>
                <button id="change-password-btn" type="button" class="secondary-btn">更新密码</button>
                <p id="password-status" class="stats"></p>
              </fieldset>
              <details class="settings-advanced">
                <summary>高级：首次初始化设置</summary>
                <p class="stats">以下仅在数据库首次初始化时使用，正常运行后请勿随意修改。</p>
                <label class="field"><span>默认用户名</span>
                  <input id="setting-default-admin-user" type="text"></label>
                <label class="field"><span>默认密码</span>
                  <input id="setting-default-admin-password" type="password" placeholder="留空则不修改"></label>
                <label class="field"><span>Session Secret</span>
                  <input id="setting-session-secret" type="password" placeholder="留空则不修改"></label>
              </details>
            </div>

            <!-- AI 与搜索 -->
            <div class="settings-pane hidden" data-settings-pane="ai">
              <p class="settings-desc">AI 线索发现依赖 LLM；搜索引擎 Key 为可选增强，全部留空时默认使用 DuckDuckGo。</p>
              <fieldset>
                <legend>LLM（AI 线索发现必填）</legend>
                <label class="field"><span>API Key</span>
                  <input id="setting-llm-api-key" type="password" placeholder="留空则不修改"></label>
                <label class="field"><span>Base URL</span>
                  <input id="setting-llm-base-url" type="url"></label>
                <label class="field"><span>Model</span>
                  <input id="setting-llm-model" type="text"></label>
              </fieldset>
              <fieldset>
                <legend>搜索引擎 API（可选）</legend>
                <label class="field"><span>Tavily API Key</span>
                  <input id="setting-tavily-api-key" type="password" placeholder="留空则不修改"></label>
                <label class="field"><span>SerpAPI Key</span>
                  <input id="setting-serpapi-key" type="password" placeholder="留空则不修改"></label>
                <label class="field"><span>Bing Search Key</span>
                  <input id="setting-bing-search-key" type="password" placeholder="留空则不修改"></label>
              </fieldset>
            </div>

            <!-- 线索导入 -->
            <div class="settings-pane hidden" data-settings-pane="import">
              <p class="settings-desc">控制哪些邮箱可以被导入。白名单非空时仅导入匹配项；黑名单始终排除。</p>
              <fieldset>
                <legend>导入过滤（黑名单 / 白名单）</legend>
                <p class="stats">每行一条：域名（如 <code>example.com</code>）或带 <code>*</code> 的邮箱模式。</p>
                <label class="field"><span>黑名单</span>
                  <textarea id="setting-import-blocklist" rows="5" placeholder="noreply.com&#10;*@mailinator.com"></textarea></label>
                <label class="field"><span>白名单（留空表示不启用）</span>
                  <textarea id="setting-import-allowlist" rows="5" placeholder="yourcompany.com"></textarea></label>
              </fieldset>
            </div>

            <!-- 自动化 -->
            <div class="settings-pane hidden" data-settings-pane="automation">
              <p class="settings-desc">让服务在后台按间隔自动运行 AI 线索发现并导入联系人（按邮箱去重）。</p>
              <fieldset>
                <legend>定时任务</legend>
                <label class="field checkbox-field">
                  <input id="setting-scheduler-enabled" type="checkbox">
                  <span>启用后台定时任务</span></label>
                <label class="field"><span>检查间隔（秒）</span>
                  <input id="setting-scheduler-poll-seconds" type="number" min="30" max="3600"></label>
              </fieldset>
            </div>

            <!-- 邮件模板 -->
            <div class="settings-pane hidden" data-settings-pane="templates">
              <p class="settings-desc">用于联系人列表的 mailto 一键发信。变量：<code>{org}</code> <code>{name}</code> <code>{email}</code> <code>{asn}</code> <code>{roles}</code></p>
              <fieldset>
                <legend>邮件模板</legend>
                <div id="email-templates-list" class="template-list"></div>
                <label class="field"><span>模板名称</span>
                  <input id="template-name" type="text" placeholder="例如：Peering 初次联系"></label>
                <label class="field"><span>主题</span>
                  <input id="template-subject" type="text" placeholder="Peering inquiry — {org}"></label>
                <label class="field"><span>正文</span>
                  <textarea id="template-body" rows="6" placeholder="Hi {name},&#10;&#10;We would like to discuss peering with {org} (AS{asn})…"></textarea></label>
                <div class="controls">
                  <button id="save-template-btn" type="button" class="secondary-btn">保存模板</button>
                </div>
                <p id="template-status" class="stats"></p>
              </fieldset>
            </div>

            <!-- 数据备份 -->
            <div class="settings-pane hidden" data-settings-pane="backup">
              <p class="settings-desc">下载完整 SQLite 数据库文件，用于迁移或灾难恢复。</p>
              <fieldset>
                <legend>数据备份</legend>
                <button id="download-backup-btn" type="button" class="secondary-btn">下载数据库备份</button>
              </fieldset>
            </div>

            <div class="settings-footer" id="settings-footer">
              <button type="submit">保存设置</button>
              <p id="settings-status" class="stats"></p>
            </div>
          </form>
        </div>
      </div>
    </section>
```

> 注意：原来 `#settings-view` 的 class 是 `panel contacts-panel`，这里改成 `panel settings-view`。所有控件 id（`setting-*`、`pwd-*`、`template-*`、`download-backup-btn`、`settings-form`、`settings-status` 等）均保持不变。

- [ ] **Step 2: HTML 结构自检**

Run: `node -e "const f=require('fs').readFileSync('app/static/index.html','utf8'); const ids=['setting-llm-api-key','setting-default-admin-password','setting-import-blocklist','setting-scheduler-enabled','template-body','download-backup-btn','settings-form','settings-footer']; for(const id of ids){ if(!f.includes('id=\"'+id+'\"')) throw new Error('missing '+id); } console.log('all ids present');"`
Expected: `all ids present`

- [ ] **Step 3: Commit**

```bash
git add app/static/index.html
git commit -m "Restructure settings view into rail + paned shell"
```

---

### Task 2: 系统设置两栏布局 CSS

**Files:**
- Modify: `app/static/style.css`（替换约 770-805 行的 `.settings-form` 区块，并新增设置外壳样式）

- [ ] **Step 1: 替换并新增设置样式**

把 `app/static/style.css` 中现有的 `.settings-form { display: grid; gap: var(--space-5); max-width: 760px; }` 一行，替换为下面整段（保留其后已有的 `.settings-form fieldset`、`.settings-form legend`、`.template-list`、`.template-item*` 规则不动）：

```css
.settings-view { display: block; }

.settings-shell {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--space-5);
  margin-top: var(--space-4);
  align-items: start;
}

.settings-rail {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2);
  background: var(--surface-sunk);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  position: sticky;
  top: var(--space-4);
}

.settings-rail-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink-soft);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms ease-out, color 150ms ease-out;
}
.settings-rail-item:hover { background: var(--surface); color: var(--ink); }
.settings-rail-item.active {
  background: var(--surface);
  color: var(--petrol-ink);
  border-color: var(--line);
  box-shadow: var(--shadow-rest);
}
.settings-rail-item:focus-visible {
  outline: 2px solid var(--petrol);
  outline-offset: 2px;
}

.rail-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--r-pill);
  background: var(--ink-muted);
  flex-shrink: 0;
}
.rail-dot.on { background: var(--positive); }

.settings-form { display: block; max-width: 720px; }
.settings-pane { display: grid; gap: var(--space-5); }
.settings-pane.hidden { display: none; }

.settings-desc {
  margin: 0;
  color: var(--ink-muted);
  font-size: var(--text-sm);
  line-height: 1.55;
}

.settings-advanced {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 0 var(--space-5);
  background: var(--surface);
}
.settings-advanced > summary {
  cursor: pointer;
  padding: var(--space-3) 0;
  font-weight: 650;
  font-size: var(--text-sm);
  color: var(--ink);
}
.settings-advanced[open] { padding-bottom: var(--space-5); }
.settings-advanced > .field,
.settings-advanced > .stats { margin-top: var(--space-3); }

.settings-footer {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--line);
}
.settings-footer.hidden { display: none; }
.settings-footer .stats { margin: 0; }
```

> 若 `--shadow-rest` 变量在 style.css 中不存在，改用现有的 resting 阴影变量名（在文件顶部 `:root` 中查找 `--shadow`），或临时用 `box-shadow: 0 1px 2px oklch(0.28 0.03 256 / 0.06);`。实现时先 `grep -n "shadow" app/static/style.css` 确认变量名。

- [ ] **Step 2: 新增移动端横滚规则**

在 `app/static/style.css` 末尾的 `@media (max-width: ...)` 响应式块中（文件已有 `.layout { grid-template-columns: 1fr; }` 的媒体查询，约 991 行），在该媒体查询 `{ ... }` 内追加：

```css
  .settings-shell { grid-template-columns: 1fr; }
  .settings-rail {
    flex-direction: row;
    overflow-x: auto;
    position: static;
    flex-wrap: nowrap;
  }
  .settings-rail-item { white-space: nowrap; }
```

- [ ] **Step 3: 验证变量存在**

Run: `grep -nE "shadow-rest|--shadow" app/static/style.css | head`
Expected: 找到 resting 阴影变量；若与 `--shadow-rest` 不符，按 Step 1 注释修正引用。

- [ ] **Step 4: Commit**

```bash
git add app/static/style.css
git commit -m "Style settings two-pane shell with rail and sticky footer"
```

---

### Task 3: 系统设置分类切换 + 状态点 + footer 可见性（JS）

**Files:**
- Modify: `app/static/app.js`（新增分类切换逻辑；扩展 `loadSettingsForm`）

- [ ] **Step 1: 新增分类切换 + footer 控制函数**

在 `app/static/app.js` 中 `loadSettingsForm` 函数（约 885 行）之前插入：

```js
const SETTINGS_FORM_CATS = new Set(["account", "ai", "import", "automation"]);
let activeSettingsCat = "account";

function switchSettingsCat(cat) {
  activeSettingsCat = cat;
  document.querySelectorAll(".settings-rail-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.settingsCat === cat);
  });
  document.querySelectorAll(".settings-pane").forEach((pane) => {
    pane.classList.toggle("hidden", pane.dataset.settingsPane !== cat);
  });
  const footer = document.getElementById("settings-footer");
  footer.classList.toggle("hidden", !SETTINGS_FORM_CATS.has(cat));
}

function updateSettingsRailDots(data) {
  const aiDot = document.getElementById("rail-dot-ai");
  const aiOn = Boolean(data.llm_api_key_configured);
  aiDot.classList.toggle("on", aiOn);
  aiDot.title = aiOn ? "LLM 已配置" : "LLM 未配置";

  const autoDot = document.getElementById("rail-dot-automation");
  const autoOn = data.scheduler_enabled === "1";
  autoDot.classList.toggle("on", autoOn);
  autoDot.title = autoOn ? "定时任务已启用" : "定时任务未启用";
}
```

- [ ] **Step 2: 在 `loadSettingsForm` 末尾刷新状态点**

在 `loadSettingsForm`（约 885-907 行）函数体末尾、`settingsStatusEl.textContent = "";` 之后，添加一行：

```js
  updateSettingsRailDots(data);
```

- [ ] **Step 3: 绑定分类轨点击 + 初始化激活态**

在 `app/static/app.js` 底部事件绑定区（`tabs.forEach(...)` 附近，约 1512 行）添加：

```js
document.querySelectorAll(".settings-rail-item").forEach((btn) => {
  btn.addEventListener("click", () => switchSettingsCat(btn.dataset.settingsCat));
});
```

- [ ] **Step 4: 切到设置页时确保激活当前分类**

在 `switchView` 函数（约 1097 行）的 `else if (view === "settings")` 分支内，`loadSettingsForm()` 调用之后添加：

```js
    switchSettingsCat(activeSettingsCat);
```

- [ ] **Step 5: 语法校验**

Run: `node --check app/static/app.js`
Expected: 无输出（退出码 0）

- [ ] **Step 6: 可视化验证**

启动应用（`uvicorn app.main:app --port 8000` 或现有运行方式），登录后进入「系统设置」：六个分类可点击切换、输入切换后不丢失、AI/自动化状态点随配置变化、templates/backup 分类隐藏底部「保存设置」、其余分类显示。窄屏时分类轨横向滚动。

- [ ] **Step 7: Commit**

```bash
git add app/static/app.js
git commit -m "Wire settings category switching, rail status dots, footer visibility"
```

---

## Part B — AI 线索发现

### Task 4: 渠道进度面板 — HTML 容器 + CSS

**Files:**
- Modify: `app/static/index.html`（在 AI 输入面板内，替换 `#ai-progress` 区域）
- Modify: `app/static/style.css`（新增渠道面板样式）

- [ ] **Step 1: 在 AI 输入面板加入渠道面板容器**

在 `app/static/index.html` 中，把现有的（约 128-131 行）：

```html
        <div id="ai-progress" class="progress hidden">
          <div class="progress-bar"><div id="ai-progress-fill"></div></div>
          <p id="ai-progress-text">准备中…</p>
        </div>
```

替换为：

```html
        <div id="ai-channels" class="ai-channels hidden"></div>

        <div id="ai-progress" class="progress hidden">
          <div class="progress-bar"><div id="ai-progress-fill"></div></div>
          <p id="ai-progress-text">准备中…</p>
        </div>
```

- [ ] **Step 2: 新增渠道面板样式**

在 `app/static/style.css` 的 `.ai-sources { ... }` 规则（约 649-655 行）之后追加：

```css
.ai-channels {
  display: grid;
  gap: var(--space-1);
  margin-top: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface-sunk);
}
.ai-channels.hidden { display: none; }

.ai-channel-row {
  display: grid;
  grid-template-columns: 16px 84px 64px 1fr;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  font-size: var(--text-sm);
}
.ai-channel-row + .ai-channel-row { border-top: 1px solid var(--line); }

.ai-channel-icon { text-align: center; font-family: var(--font-mono); }
.ai-channel-name { color: var(--ink); font-weight: 600; }
.ai-channel-count {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--ink-soft);
  text-align: right;
}
.ai-channel-preview {
  font-family: var(--font-mono);
  color: var(--ink-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ai-channel-row.state-idle .ai-channel-icon { color: var(--ink-muted); }
.ai-channel-row.state-active .ai-channel-icon { color: var(--petrol); }
.ai-channel-row.state-done .ai-channel-icon { color: var(--positive); }
.ai-channel-row.state-failed .ai-channel-icon { color: var(--danger); }
.ai-channel-row.state-failed .ai-channel-preview { color: var(--danger); }
```

> 实现前用 `grep -nE "font-mono|--font-mono|font-family.*mono" app/static/style.css` 确认 mono 字体变量名；若项目用的是其它变量（如 `--mono`），替换上面的 `var(--font-mono)`。

- [ ] **Step 3: 语法/存在性校验**

Run: `node -e "const f=require('fs').readFileSync('app/static/index.html','utf8'); if(!f.includes('id=\"ai-channels\"')) throw new Error('missing ai-channels'); console.log('ok');"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/static/index.html app/static/style.css
git commit -m "Add channel progress panel container and styles"
```

---

### Task 5: 渠道面板状态机 + 渲染，接入流事件，删除死代码

**Files:**
- Modify: `app/static/app.js`

- [ ] **Step 1: 新增渠道面板元素引用与状态**

在 `app/static/app.js` 顶部引用区（`const aiLeadsBody = ...` 之后，约 93 行）添加：

```js
const aiChannelsEl = document.getElementById("ai-channels");
```

并在 `let aiLeads = [];`（约 116 行）之后添加：

```js
const CHANNEL_DEFS = [
  { key: "peeringdb", name: "PeeringDB" },
  { key: "web_search", name: "搜索引擎" },
  { key: "web_regex", name: "网页解析" },
  { key: "llm_extract", name: "LLM 提取" },
  { key: "arin", name: "ARIN RDAP" },
  { key: "scoring", name: "LLM 评分" },
];
let channelState = {};
```

- [ ] **Step 2: 新增状态机与渲染函数**

在 `renderAiSources` 函数（约 1191 行）之后添加：

```js
function resetChannelPanel() {
  channelState = {};
  for (const def of CHANNEL_DEFS) {
    channelState[def.key] = { state: "idle", count: "", preview: "" };
  }
  renderChannelPanel();
}

function setChannel(key, patch) {
  if (!channelState[key]) channelState[key] = { state: "idle", count: "", preview: "" };
  Object.assign(channelState[key], patch);
  renderChannelPanel();
}

const CHANNEL_ICON = { idle: "·", active: "◐", done: "✓", failed: "×" };

function renderChannelPanel() {
  aiChannelsEl.classList.remove("hidden");
  aiChannelsEl.innerHTML = CHANNEL_DEFS.map((def) => {
    const s = channelState[def.key] || { state: "idle", count: "", preview: "" };
    return `
      <div class="ai-channel-row state-${s.state}">
        <span class="ai-channel-icon">${CHANNEL_ICON[s.state]}</span>
        <span class="ai-channel-name">${escapeHtml(def.name)}</span>
        <span class="ai-channel-count">${escapeHtml(String(s.count ?? ""))}</span>
        <span class="ai-channel-preview" title="${escapeHtml(s.preview || "")}">${escapeHtml(s.preview || "")}</span>
      </div>`;
  }).join("");
}
```

- [ ] **Step 3: 在 `runLeadDiscovery` 开始处初始化面板**

在 `runLeadDiscovery`（约 1222 行）函数内，把现有的 `aiSourcesEl.classList.add("hidden");`（约 1236 行）之后添加：

```js
  resetChannelPanel();
```

- [ ] **Step 4: 在流事件处理中驱动渠道面板**

在 `runLeadDiscovery` 的事件循环里，将现有的 `if (payload.type === "source_result")` 分支（约 1292-1294 行）替换为：

```js
        if (payload.type === "source_result") {
          const preview = (payload.preview || []).join(" · ");
          setChannel(payload.source, { state: "done", count: payload.count, preview });
          aiProgressText.textContent = `${payload.source} 返回 ${payload.count} 条`;
        }
```

在该分支之后、`if (payload.type === "progress")` 之前，新增 ARIN 与 scoring 的驱动：

```js
        if (payload.type === "status" && /评估|评分/.test(payload.message || "")) {
          setChannel("scoring", { state: "active" });
        }
```

将现有的 `if (payload.type === "progress")` 分支（约 1300-1304 行）替换为：

```js
        if (payload.type === "progress") {
          const percent = Math.round((payload.index / payload.total) * 100);
          aiProgressFill.style.width = `${percent}%`;
          aiProgressText.textContent = `${payload.message}（${payload.index}/${payload.total}）`;
          setChannel("arin", {
            state: payload.index >= payload.total ? "done" : "active",
            count: `${payload.index}/${payload.total}`,
            preview: payload.network || `AS${payload.asn}`,
          });
        }
```

- [ ] **Step 5: `done` 时收尾 scoring 渠道；删除 `networks` 死分支**

在事件循环中删除整个 `if (payload.type === "networks") { ... }` 分支（约 1296-1298 行，后端从不发送）。

在 `if (payload.type === "done")` 分支开头（约 1316 行，`aiProgressFill.style.width = "100%";` 之后）添加：

```js
          setChannel("scoring", { state: "done", count: (payload.leads || aiLeads).length });
```

- [ ] **Step 6: 渠道部分失败时标红对应行**

在事件循环中，当前 `extract_leads_from_web` 失败会发 `{type:"status", message:"网页线索提取部分失败：..."}`。在 `status` 处理处（约 1283-1285 行）之后添加：

```js
        if (payload.type === "status" && /提取部分失败/.test(payload.message || "")) {
          setChannel("llm_extract", { state: "failed", preview: payload.message });
        }
```

- [ ] **Step 7: 语法校验**

Run: `node --check app/static/app.js`
Expected: 无输出

- [ ] **Step 8: 可视化验证**

进入「AI 线索发现」，点「AI 开始找线索」：渠道面板出现并逐行从 `·` 待命 → `◐` 进行中 → `✓` 完成，计数与预览正确；ARIN 行显示 `x/total`；评分行最后变 `✓`。确认控制台无 `networks` 相关报错。

- [ ] **Step 9: Commit**

```bash
git add app/static/app.js
git commit -m "Drive live channel panel from discovery stream; drop dead networks branch"
```

---

### Task 6: 取消 / 重试

**Files:**
- Modify: `app/static/index.html`（增加重试按钮容器）
- Modify: `app/static/app.js`

- [ ] **Step 1: HTML — 在结果区操作栏加重试按钮**

在 `app/static/index.html` 的 AI 结果区操作栏（约 140-142 行）中，把：

```html
          <div class="results-actions">
            <button id="import-leads-btn" type="button" class="success-btn" disabled>导入选中线索</button>
          </div>
```

替换为：

```html
          <div class="results-actions">
            <button id="retry-discover-btn" type="button" class="secondary-btn hidden">重试</button>
            <button id="import-leads-btn" type="button" class="success-btn" disabled>导入选中线索</button>
          </div>
```

- [ ] **Step 2: JS — 元素引用与运行状态标志**

在 `app/static/app.js` 顶部引用区（`const importLeadsBtn = ...` 之后）添加：

```js
const retryDiscoverBtn = document.getElementById("retry-discover-btn");
```

在 `let channelState = {};` 之后添加：

```js
let discoverController = null;
let lastDiscoverQuery = "";
```

- [ ] **Step 3: JS — 按钮态切换辅助函数**

在 `runLeadDiscovery` 函数之前添加：

```js
function setDiscoverRunning(running) {
  if (running) {
    discoverBtn.textContent = "取消";
    discoverBtn.classList.add("danger-btn");
    discoverBtn.disabled = false;
    retryDiscoverBtn.classList.add("hidden");
  } else {
    discoverBtn.textContent = "AI 开始找线索";
    discoverBtn.classList.remove("danger-btn");
    discoverBtn.disabled = !llmConfigured;
  }
}
```

> 若 `.danger-btn` 在 style.css 中不存在，在 Task 8 的 CSS 步骤里一并添加（见该任务）。

- [ ] **Step 4: JS — 改造 `runLeadDiscovery` 支持取消**

在 `runLeadDiscovery` 函数中做三处修改：

(a) 函数开头（`const query = ...` 之前）加入"运行中则点击=取消"的短路：

```js
  if (discoverController) {
    discoverController.abort();
    return;
  }
```

(b) 把现有的 `discoverBtn.disabled = true;`（约 1240 行）替换为：

```js
  lastDiscoverQuery = query;
  discoverController = new AbortController();
  setDiscoverRunning(true);
  retryDiscoverBtn.classList.add("hidden");
```

(c) 把 `fetch("/api/leads/discover/stream", { ... })` 的选项对象加上 `signal`：

```js
    const response = await fetch("/api/leads/discover/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      signal: discoverController.signal,
      body: JSON.stringify({
        query,
        min_score: Number(minScoreInput.value) || 60,
        delay: 0.5,
        auto_import: autoImportInput.checked,
      }),
    });
```

(d) 把 `catch (error) { ... } finally { ... }`（约 1333-1338 行）替换为：

```js
  } catch (error) {
    if (error.name === "AbortError") {
      aiProgressText.textContent = "已取消";
    } else {
      aiProgressText.textContent = "失败";
      showLeadsError(error.message || "AI 线索发现失败");
    }
  } finally {
    discoverController = null;
    setDiscoverRunning(false);
  }
```

> `showLeadsError` 在 Task 8 定义。若 Task 8 尚未完成，本步骤可临时用 `alert(error.message || "AI 线索发现失败");`，并在 Task 8 替换。

- [ ] **Step 5: JS — 绑定重试**

在底部事件绑定区，`discoverBtn.addEventListener("click", runLeadDiscovery);`（约 1387 行）之后添加：

```js
retryDiscoverBtn.addEventListener("click", () => {
  if (lastDiscoverQuery) {
    leadQueryInput.value = lastDiscoverQuery;
  }
  runLeadDiscovery();
});
```

- [ ] **Step 6: 语法校验**

Run: `node --check app/static/app.js`
Expected: 无输出

- [ ] **Step 7: 可视化验证**

开始发现后按钮变「取消」；点击取消，流停止、进度显示「已取消」、按钮恢复「AI 开始找线索」、已得渠道结果保留。无结果或失败时出现「重试」并能重跑。

- [ ] **Step 8: Commit**

```bash
git add app/static/index.html app/static/app.js
git commit -m "Add cancel (AbortController) and retry to lead discovery"
```

---

### Task 7: 线索详情模态 + 修复 AI 行勾选联动

**Files:**
- Modify: `app/static/index.html`（新增详情模态）
- Modify: `app/static/style.css`（复用 notes 模态样式，新增详情排版）
- Modify: `app/static/app.js`

- [ ] **Step 1: HTML — 在 `#ai-leads-view` 末尾加入详情模态**

在 `app/static/index.html` 中 `<section id="ai-leads-view" ...>` 的闭合 `</section>`（约 167 行）**之前**插入：

```html
      <div id="lead-detail-modal" class="contact-notes-modal hidden" role="dialog" aria-labelledby="lead-detail-title">
        <div class="contact-notes-backdrop" data-close-detail></div>
        <div class="contact-notes-dialog">
          <div class="contact-notes-head">
            <h3 id="lead-detail-title">线索详情</h3>
            <button type="button" class="link-btn" data-close-detail>关闭</button>
          </div>
          <div id="lead-detail-body" class="lead-detail-body"></div>
          <label class="field checkbox-field lead-detail-import">
            <input id="lead-detail-import" type="checkbox">
            <span>导入此线索</span>
          </label>
        </div>
      </div>
```

> 实现前用 `grep -n "contact-notes-dialog\|contact-notes-head" app/static/index.html` 确认现有模态内部 class 名；若不同（如 `.contact-notes-panel`），按实际类名替换 dialog/head 容器，保持与既有模态一致的结构。

- [ ] **Step 2: CSS — 详情排版**

在 `app/static/style.css` 的 `.template-item-actions { ... }` 之后（或任意合适位置）追加：

```css
.lead-detail-body { display: grid; gap: var(--space-3); margin: var(--space-4) 0; }
.lead-detail-row { display: grid; grid-template-columns: 88px 1fr; gap: var(--space-3); align-items: start; }
.lead-detail-row > .k {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink-muted);
}
.lead-detail-row > .v { color: var(--ink); line-height: 1.55; word-break: break-word; }
.lead-detail-row > .v.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.lead-detail-import { margin-top: var(--space-2); }
```

> 用 `grep -nE "text-xs|--text-xs" app/static/style.css` 确认字号变量名，必要时替换。

- [ ] **Step 3: JS — 元素引用**

在顶部引用区添加：

```js
const leadDetailModal = document.getElementById("lead-detail-modal");
const leadDetailBody = document.getElementById("lead-detail-body");
const leadDetailImport = document.getElementById("lead-detail-import");
let detailLeadIndex = null;
```

- [ ] **Step 4: JS — 在线索行加「详情」按钮**

在 `renderAiLeads` 的行模板（约 1153-1162 行）中，把最后一格 AI 理由那格：

```js
      <td>${escapeHtml(lead.lead_reason || lead.source_detail || "—")}</td>
```

替换为：

```js
      <td>
        ${escapeHtml(lead.lead_reason || lead.source_detail || "—")}
        <button type="button" class="link-btn lead-detail-btn" data-index="${index}">详情</button>
      </td>
```

- [ ] **Step 5: JS — 打开/关闭详情与字段渲染**

在 `formatSource` 函数之后添加：

```js
function openLeadDetail(index) {
  const lead = aiLeads[index];
  if (!lead) return;
  detailLeadIndex = index;
  const roles = (lead.roles || []).map((r) => `<span class="role-tag">${escapeHtml(r)}</span>`).join(" ") || "—";
  const rows = [
    ["组织", escapeHtml(lead.org || lead.network_name || "—"), false],
    ["邮箱", `<a class="email-link" href="mailto:${lead.email}">${escapeHtml(lead.email || "—")}</a>`, true],
    ["ASN", lead.asn ? `AS${lead.asn}` : "—", true],
    ["Role", roles, false],
    ["来源", escapeHtml(formatSource(lead)), false],
    ["来源详情", escapeHtml(lead.source_detail || "—"), false],
    ["网络名", escapeHtml(lead.network_name || "—"), false],
    ["匹配关键词", escapeHtml(lead.matched_keyword || "—"), true],
    ["AI 评分", `<span class="score-badge">${lead.lead_score || 0}</span>`, false],
    ["AI 理由", escapeHtml(lead.lead_reason || "—"), false],
  ];
  leadDetailBody.innerHTML = rows
    .map(([k, v, mono]) => `<div class="lead-detail-row"><span class="k">${k}</span><span class="v${mono ? " mono" : ""}">${v}</span></div>`)
    .join("");
  ensureLeadSelected(lead);
  leadDetailImport.checked = lead._selected !== false;
  leadDetailModal.classList.remove("hidden");
}

function closeLeadDetail() {
  detailLeadIndex = null;
  leadDetailModal.classList.add("hidden");
}
```

- [ ] **Step 6: JS — 事件绑定（详情打开、关闭、勾选联动，及修复行内勾选）**

在底部事件绑定区添加：

```js
aiLeadsBody.addEventListener("click", (event) => {
  const btn = event.target.closest(".lead-detail-btn");
  if (btn) openLeadDetail(Number(btn.dataset.index));
});

aiLeadsBody.addEventListener("change", (event) => {
  const check = event.target.closest(".row-import-check");
  if (!check || check.dataset.kind !== "ai") return;
  const lead = aiLeads[Number(check.dataset.index)];
  if (lead) lead._selected = check.checked;
  updateAiLeadsStats();
});

leadDetailModal.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-detail]")) closeLeadDetail();
});

leadDetailImport.addEventListener("change", () => {
  if (detailLeadIndex === null) return;
  const lead = aiLeads[detailLeadIndex];
  if (lead) lead._selected = leadDetailImport.checked;
  renderAiLeads();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !leadDetailModal.classList.contains("hidden")) closeLeadDetail();
});
```

> Task 6 的取消按钮也可接受 Esc，但本计划仅为详情模态绑定 Esc，避免误触取消发现。

- [ ] **Step 7: 语法校验**

Run: `node --check app/static/app.js`
Expected: 无输出

- [ ] **Step 8: 可视化验证**

跑出线索后，点行内「详情」弹出模态、字段完整且机器字段为等宽对齐；模态内勾「导入此线索」后关闭，列表对应行复选框同步；直接在列表里取消勾选，下方「已选 N / 共 M」实时变化、导入时只导入勾选项；Esc/点背景可关闭。

- [ ] **Step 9: Commit**

```bash
git add app/static/index.html app/static/style.css app/static/app.js
git commit -m "Add lead detail modal and wire AI row import selection"
```

---

### Task 8: 空 / 错误状态引导

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/style.css`

- [ ] **Step 1: CSS — 状态卡与 danger 按钮**

在 `app/static/style.css` 追加：

```css
.danger-btn {
  background: var(--danger);
  color: var(--on-accent);
  border-color: transparent;
}
.danger-btn:hover { filter: brightness(0.94); }

.leads-state {
  display: grid;
  gap: var(--space-3);
  justify-items: start;
  padding: var(--space-5);
  border: 1px dashed var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  color: var(--ink-soft);
}
.leads-state.error { border-color: var(--danger); color: var(--danger); }
.leads-state .hint { color: var(--ink-muted); font-size: var(--text-sm); }
```

> 用 `grep -nE "on-accent|--on-accent" app/static/style.css` 确认按钮前景变量名。

- [ ] **Step 2: HTML — 在结果面板加入状态卡容器**

在 `app/static/index.html` 的 AI 结果面板里，`<div class="table-wrap">`（约 145 行）**之前**插入：

```html
        <div id="ai-leads-state" class="leads-state hidden"></div>
```

- [ ] **Step 3: JS — 引用与状态渲染函数**

在顶部引用区添加：

```js
const aiLeadsStateEl = document.getElementById("ai-leads-state");
```

在 `renderAiLeads` 函数之前添加：

```js
function hideLeadsState() {
  aiLeadsStateEl.classList.add("hidden");
  aiLeadsStateEl.innerHTML = "";
}

function showLeadsState(html, isError = false) {
  aiLeadsStateEl.className = `leads-state${isError ? " error" : ""}`;
  aiLeadsStateEl.innerHTML = html;
}

function showLeadsError(message) {
  showLeadsState(
    `<p>线索发现出错：${escapeHtml(message)}</p>
     <button type="button" class="secondary-btn" id="leads-state-retry">重试</button>`
  );
  const btn = document.getElementById("leads-state-retry");
  if (btn) btn.addEventListener("click", () => runLeadDiscovery());
}

function showLeadsEmpty() {
  showLeadsState(
    `<p>没有找到符合条件的线索。</p>
     <p class="hint">建议：调低「最低匹配分」，或用更宽泛的关键词描述目标客户。</p>
     <button type="button" class="secondary-btn" id="leads-state-retry">重试</button>`
  );
  const btn = document.getElementById("leads-state-retry");
  if (btn) btn.addEventListener("click", () => runLeadDiscovery());
}

function showLeadsNeedLlm() {
  showLeadsState(
    `<p>AI 线索发现需要先配置 LLM。</p>
     <p class="hint">前往「系统设置 → AI 与搜索」填写 API Key。</p>
     <button type="button" class="primary-btn" id="leads-state-goto-settings">去系统设置</button>`
  );
  const btn = document.getElementById("leads-state-goto-settings");
  if (btn) {
    btn.addEventListener("click", () => {
      switchView("settings");
      switchSettingsCat("ai");
    });
  }
}
```

> 若主按钮默认无 `.primary-btn` 类（项目里 `<button>` 默认即 primary 样式），把上面的 `class="primary-btn"` 改为不带 class 的 `<button type="button" id="leads-state-goto-settings">去系统设置</button>`。实现前用 `grep -n "primary-btn" app/static/style.css` 确认。

- [ ] **Step 4: JS — 在关键节点切换状态卡**

(a) `runLeadDiscovery` 开始处（`resetChannelPanel();` 之后）添加 `hideLeadsState();`。

(b) `renderAiLeads` 函数开头（`aiLeadsBody.innerHTML = "";` 之后）添加：当有线索时隐藏状态卡：

```js
  if (aiLeads.length > 0) hideLeadsState();
```

(c) 在 `done` 事件分支末尾（处理完 `payload.leads`、`payload.import` 之后）添加无结果判断：

```js
          if ((payload.leads || aiLeads).length === 0) {
            showLeadsEmpty();
          }
```

(d) `loadLlmStatus` 中 LLM 未配置分支（约 1210-1213 行，`discoverBtn.disabled = true;` 之后）添加：

```js
      showLeadsNeedLlm();
```

并在 LLM 已配置分支（`discoverBtn.disabled = false;` 之后）添加 `hideLeadsState();`。

- [ ] **Step 5: 确认 Task 6 中的 `showLeadsError` 引用已生效**

若 Task 6 Step 4(d) 当时用了临时 `alert`，现在替换为 `showLeadsError(error.message || "AI 线索发现失败");`。

- [ ] **Step 6: 语法校验**

Run: `node --check app/static/app.js`
Expected: 无输出

- [ ] **Step 7: 可视化验证**

- 未配置 LLM（清空设置里的 API Key 后重载）：结果区出现引导卡，点「去系统设置」跳转并自动激活「AI 与搜索」分类。
- 用极高最低匹配分（如 100）跑一次造成无结果：出现「没有找到…」+ 重试。
- 断网或后端报错：出现红框错误卡 + 重试。

- [ ] **Step 8: Commit**

```bash
git add app/static/index.html app/static/style.css app/static/app.js
git commit -m "Add empty/error/needs-LLM guidance states for lead discovery"
```

---

### Task 9: 记录下一阶段路线 + 全量验证

**Files:**
- Modify: `FEATURE_PLAN.md`

- [ ] **Step 1: 在 `FEATURE_PLAN.md` 增补下一阶段条目**

在 `FEATURE_PLAN.md` 的「第三阶段」表格之后、「## Loop 指令」之前，新增：

```markdown
## 第四阶段（规划中）

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 19 | 更多搜索渠道 | pending | 在 app/sources 下新增渠道（如 RIPE/APNIC RDAP、行业目录） |
| 20 | 外部 agent 集成 | pending | 可选接入外部线索 agent（"pi agent"）：定义渠道插件接口后接入 |
```

- [ ] **Step 2: Commit**

```bash
git add FEATURE_PLAN.md
git commit -m "Record next-phase channel/agent expansion in feature plan"
```

- [ ] **Step 3: 全量语法校验**

Run: `node --check app/static/app.js && echo OK`
Expected: `OK`

- [ ] **Step 4: 启动应用做整体回归（用 run/verify 技能或手动）**

启动后逐项确认：
1. 系统设置六分类切换、保存仍写入全部表单字段（账号/AI/导入/自动化）、状态点正确、移动端横滚、键盘焦点环可见。
2. AI 线索发现：渠道面板逐行点亮；取消可中断并复位；无结果/失败有重试；未配置 LLM 有去设置引导且能跳转激活 AI 分类；详情模态字段完整、导入勾选与列表双向同步。
3. 浏览器控制台无报错；无遗留 `networks` 死代码。

- [ ] **Step 5: 收尾**

确认所有任务 commit 完成，工作区干净（`git status`）。

---

## Self-Review

**Spec 覆盖：**
- Part A 左侧分类导航 + 右侧内容 → Task 1（HTML 外壳/6 分类/高级折叠/footer）、Task 2（CSS 两栏/状态点/移动横滚）、Task 3（切换/状态点/footer 可见性/保存复用）。✓
- B1 实时渠道面板 → Task 4（容器+CSS）、Task 5（状态机+接入+删死代码）。✓
- B2 取消/重试 → Task 6。✓
- B3 线索详情 + 勾选联动修复 → Task 7。✓
- B4 空/错误/未配置态 → Task 8。✓
- pi-agent/更多渠道记入路线 → Task 9。✓

**Placeholder 扫描：** 无 TBD/TODO；每个改动步骤含具体代码与命令。对依赖项目既有 CSS 变量名处，均给出 `grep` 确认指令与替代方案（非占位，是防御性校验）。

**类型/命名一致性：** `channelState`/`setChannel`/`resetChannelPanel`/`renderChannelPanel`、`discoverController`/`lastDiscoverQuery`、`switchSettingsCat`/`activeSettingsCat`/`SETTINGS_FORM_CATS`、`showLeadsState`/`showLeadsError`/`showLeadsEmpty`/`showLeadsNeedLlm`/`hideLeadsState`、`openLeadDetail`/`closeLeadDetail`/`detailLeadIndex` 在定义与引用处一致。Task 6 临时 `showLeadsError` 引用在 Task 8 Step 5 收口。✓

**验证现实性：** 无 JS 测试框架，统一用 `node --check` + 运行应用可视化验证，已在 header 说明，未虚构测试命令。✓
