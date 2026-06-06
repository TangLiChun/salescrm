# Pi Agent 商用化 · 子项目 1:可靠性 + 测试地基

- 日期:2026-06-06
- 状态:已批准设计,待生成实现计划
- 作者:Pi / Sales CRM 团队
- 范围:Pi agent(`app/agent_chat.py` 及相关模块)的可靠性加固与自动化测试地基
- 改造方案:Approach B(重点抽离)

## 0. 这是更大计划的第一步

把 Pi agent 完善到"可商用"被拆为三个有序子项目,各自走独立的 spec → plan → 实现循环:

1. **可靠性 + 测试地基**(本文档)
2. 可观测 + 安全加固(LLM 用量/成本计量、审计日志、错误追踪、密钥管理、注入/越权防护、限流)
3. 多租户商用化(每用户 token、数据隔离、配额、计费;开始前需确认商用形态)

推进顺序严格为 1 → 2 → 3:先把地基与稳定性打牢,后两块才不会建在流沙上。本子项目**只碰可靠性与测试,不加任何新功能**。

## 1. 背景与根因

Pi 是 Sales CRM 内的 AI 助手,帮销售/BD 操作网络运营商联系人库(ASN role 邮箱查询、线索发现、联系人管理、定时任务、社交抓取等),约 28 个工具,基于 DeepSeek V4(OpenAI 兼容协议)。

近几十个 commit 几乎全是 "Fix Pi…" 类可靠性救火(空回复、只发开场白不调工具、无效 tool_call 重试死循环、流中断误报、tool JSON 漏进气泡)。根因有三:

1. **无测试的巨石主循环。** `app/agent_chat.py` 约 2000 行,核心 agent 循环([agent_chat.py:2004-2268](../../../app/agent_chat.py))是 `for round in range(MAX_TOOL_ROUNDS): while True:` 的深层嵌套,约十几个分支处理 DeepSeek 的各种畸形输出。逻辑全无测试,改一处常碰坏另一处。文件含 26 个无测试的 `_` 启发式辅助函数。
2. **假流式 + 零重试。** [llm.py:321-322](../../../app/llm.py) 用 `urllib.request.urlopen(req).read()` 一次性读完整个响应再回放 deltas(并非边到边流式),且同步 urllib 丢进线程跑;对 429/5xx/超时/连接错**完全没有重试退避**,直接 yield 错误。
3. **零自动化测试。** 项目无任何 test、无 pytest/ruff、无 CI;只有部署后的 `scripts/smoke_check.py`(查 DB/schema/静态 HTML)与 `scripts/check.sh`(docker 健康)。每次修 bug 靠手测,无回归网。

环境事实:GitHub 仓库 `TangLiChun/salescrm`(CI 用 GitHub Actions);生产运行时 **Python 3.12**(Dockerfile `python:3.12-slim`);数据库为 **Postgres-only**([db.py](../../../app/db.py) 直接用 psycopg,无 SQLite 回退)。

## 2. 目标与非目标

**目标**
- 把可靠性根因(无测试循环 + 假流式 + 零重试)一次性解决,并留下回归网。
- 把两处可靠性热点抽成干净、全测试覆盖的单元:agent 决策逻辑(状态机)、LLM 客户端(真流式 + 重试)。
- 把 26 个启发式 helper 与流解析逻辑抽进聚焦的 `pi_*.py` 模块并逐个加测试。
- 建立 pytest + ruff + GitHub Actions 测试地基。

**非目标(本子项目明确不做)**
- 多租户 / 每用户 token / 配额 / 计费(子项目 3)。
- 深度可观测(成本计量、审计日志、错误追踪接入)与安全加固(注入/越权/限流、密钥管理)(子项目 2)。
- 前端 `app/static/js/modules/pi.js` 重构。
- 新增 agent 能力或工具、改动业务语义。
- 不改 `agent_chat_stream` 的对外事件契约(调用方零改动)。

## 3. 完成判据(Definition of Done)

1. `pytest` 全绿;`decide_turn` 状态机的**每个决策分支**都有单测;流解析器、tool-call 恢复、启发式函数全覆盖。
2. **每个历史 bug 都有一条具名回归测试**(见 §10 清单),且该测试在修复前能复现、修复后转绿。
3. `agent_chat_stream` 用 `FakeLLM` + 假工具的集成测试覆盖所有代表场景,**全程无网络、无真实 DB**。
4. GitHub Actions CI 绿:`ruff check` + `ruff format --check` + `pytest`(Python 3.12 + Postgres service)。
5. LLM 客户端:对 429/5xx/超时/连接错指数退避重试;真流式由解析/流式测试佐证;env-gated 的"打真 DeepSeek"冒烟测试可手动通过(CI 默认跳过)。
6. App 仍能启动(Dockerfile 的 `from app.agent_chat import agent_chat_stream` import 检查仍过);happy-path 行为由特征化测试锁定不变。
7. `agent_chat_stream` 的对外事件序列契约由测试断言保持不变;`main.py` / `app/background_jobs.py` 调用方零改动。

## 4. 目标模块结构

沿用现有 `pi_*.py` 扁平命名约定(已有 `pi_context.py`、`pi_chat_store.py`),**不引入新包层**。`agent_chat.py` 瘦身为「agent 循环驱动 + 对外门面(re-export `agent_chat_stream` 等公共符号,保证调用方零改动)」,其余抽出:

| 新模块 | 来源(现 `agent_chat.py` / `llm.py`) | 形态 |
|---|---|---|
| `app/pi_decisions.py` | 主循环 2059-2179 的分支 → `decide_turn()` 状态机 + `Decision` 类型 | 纯函数 |
| `app/pi_reply_heuristics.py` | `_meaningful_assistant_content` / `_assistant_intro_before_tools` / `_assistant_promises_tool_use` / `_user_requests_continuation` / `_assistant_response_empty` / `_infer_continuation_query` / `_make_discover_fallback_call` / `_fallback_prepared_calls` / `_content_looks_like_tool_call` / `_content_is_tool_json_fragment` | 纯函数 |
| `app/pi_tool_calls.py` | `_prepare_tool_calls` / `_parse_tool_call` / `_extract_tool_calls_from_content` / `_parse_inline_tool_calls` / `_normalize_raw_tool_entry` / `_normalize_tool_name` / `_infer_tool_name` / `_coerce_list_contacts_args` / `_ensure_tool_call_id` / `_extract_json_args` | 纯函数 |
| `app/pi_stream_parser.py` | `llm.py` 的 `_parse_sse_or_json_lines` / `_consume_stream_chunk` / `_merge_tool_call_delta` / `_apply_complete_message` | 纯函数 |
| `app/pi_llm_client.py` | 新:async httpx 真流式 + 重试/退避/超时 + 类型化事件 | I/O(可注入) |

`pi_context.py`、`pi_chat_store.py` 保持原位,只补测试。

**本子项目内延后(2026-06-06 决定):** `pi_tools.py`(~28 工具的 `AGENT_TOOLS` schema + `_run_tool` 分发表)与 `pi_events.py`(事件 TypedDict 契约)不在本子项目抽离 —— 工具分发与事件类型并非可靠性热点,拆它们是高 churn、低价值、且会动到正常工作的工具层(YAGNI)。它们暂留 `agent_chat.py`,可在后续子项目按需抽离。本决定不影响 §3 的任何 DoD 判据。`llm.py` 保留 `chat_completion`/`chat_completion_with_tools`(摘要、评分等非流式用途),其流式工具调用部分改为委托 `pi_llm_client`;SSE/delta 解析改为复用 `pi_stream_parser`。

## 5. 核心修复:agent 决策状态机

把主循环里"模型干了啥、下一步怎么办"的判断抽成一个纯函数:

```python
decide_turn(
    assistant: dict | None,
    content_buffer: str,
    *,
    user_message: str,
    history: list[dict],
    nudge_count: int,
    max_nudges: int,
) -> Decision
```

`Decision` 为显式可穷举的几种(用 dataclass / 带 tag 的联合):

- `EmitToolCalls(prepared_calls, intro_text)` — 拿到有效工具调用,执行之。
- `FinalReply(text)` — 拿到最终文本答复,结束。
- `Retry(nudge_message, reason)` — 畸形输出,追加 nudge 并重新调用 LLM(受 `max_nudges` 有界)。
- `FallbackToolCalls(prepared_calls, status_message)` — 模型拒绝调工具,合成兜底调用(如 `discover_leads` / `list_contacts`)。
- `Fail(error_message)` — 放弃,优雅收尾。

驱动器(`agent_chat_stream`)只管 I/O:调 LLM → 把结果喂给 `decide_turn` → 按 `Decision` yield 事件 / 执行工具 / 续循环。这样**所有"模型干了啥"的判断都是可穷举单测的纯逻辑**,不再散落在带 `continue`/`break`/`return` 的嵌套循环里。

`decide_turn` 的判断需复刻并显式化现有逻辑(顺序与短路关系必须由特征化测试先锁定再迁移):
1. 空助手回复 → `Retry`(达上限后 `Fail`)。
2. 有 content 无 tool_calls,但 content 内嵌 inline tool calls → 提取后 `EmitToolCalls`。
3. 有 content 无 tool_calls,且(承诺要用工具 or 用户要求继续)→ `Retry`(intro/continue nudge),达上限后 `FallbackToolCalls`。
4. 有 content 无 tool_calls,纯文本答复 → `FinalReply`。
5. 有 tool_calls 但 prepare 后为空(畸形/无效 slot)→ 先尝试从 content 提取;再不行 `Retry`;达上限后视情况 `FallbackToolCalls` 或 `Fail`。
6. 有有效 tool_calls → `EmitToolCalls`。

## 6. LLM 客户端:真流式 + 重试

新模块 `app/pi_llm_client.py`(httpx async):

- 用 `httpx.AsyncClient().stream("POST", url, ...)` **边到边**迭代 SSE 行并产出 deltas(终结假流式),直接接入事件循环,移除 `_iter_llm_stream` 的线程桥。
- **重试退避**:对 429、5xx、连接错、读超时做指数退避重试(带 jitter);尊重 `Retry-After`;**不重试** 400/401/403 等配置类错误。per-attempt 超时 + 总 deadline(沿用现有 60s/180s 量级,可配置)。
- 产出类型化事件:`content_delta` / `reasoning_delta` / `tool_call`(增量与最终装配)/ `message` / `error`。
- 保留 DeepSeek 专属处理(`thinking` / `reasoning_effort`,见 [llm.py:298-303](../../../app/llm.py))。
- 解析逻辑全部委托 `pi_stream_parser.py`(纯函数,用录制的 SSE fixture 测试)。
- 退避重试逻辑抽成与 transport 无关的共享 helper。**只有流式 agent 路径迁到 httpx**;同步路径(`chat_completion` / `chat_completion_with_tools`)保留现有 urllib transport,仅套上同一个共享退避 helper(最小 churn、低风险增量)。

**新增生产依赖:`httpx`**(加入 `requirements.txt`)。

## 7. 可测性接缝(依赖注入)

`agent_chat_stream` 增加可选注入点(生产用默认实现,测试注入假实现),默认行为与签名对调用方不变:

```python
async def agent_chat_stream(
    user_id, message, history=None, *,
    thread_id=None, cancel_check=None,
    llm_client=None,    # 默认 pi_llm_client 真实现
    tool_runner=None,   # 默认 pi_tools 的 _run_tool
) -> AsyncIterator[dict]:
```

于是循环的集成测试既不打网络也不碰 DB(注入 `FakeLLM` + 假 `tool_runner`);DB 工具单独用一次性 Postgres 测。

## 8. 测试地基

- 目录 `tests/`,`pytest` + `pytest-asyncio`,根 `pyproject.toml` 放 pytest 与 ruff 配置。
- **`FakeLLM`**(测试支点):可编排回放一串响应 —— content deltas、tool_calls(合法/畸形/分片)、空回复、HTTP 错误、超时,复刻 DeepSeek 各种怪癖。提供"第 N 次调用返回 X"的脚本能力,以测试重试与 nudge 路径。
- 测试四层:
  1. **纯单测** —— `decide_turn`、`pi_stream_parser`、`pi_tool_calls` 恢复、`pi_reply_heuristics`、`pi_context` builder,表驱动,覆盖每个分支。
  2. **集成** —— `agent_chat_stream` + `FakeLLM` + 假 `tool_runner`,断言完整事件序列(`assistant_start/delta/done`、`tool_start/result`、`context`、`done/error`),覆盖 happy path、intro-only-then-recover、empty-then-retry、invalid-toolcall-then-fallback、取消、round-cap 总结。
  3. **回归** —— §10 每条历史 bug 一条具名测试。
  4. **真 DeepSeek 冒烟**(env-gated,如 `PI_LIVE_LLM=1`)—— 单次极小真实调用,捕获协议漂移;CI 默认跳过。
- **DB 集成测试**:GitHub Actions 起 Postgres service;本地用独立 `DATABASE_URL` 指向一次性测试库;每 session 建表(复用 `init_db`)与拆除。仅"工具实际写库"的少量测试需要 DB,绝大多数测试通过注入 `tool_runner` 避开 DB。
- **特征化测试先行**:任何结构抽离前,先对现有 `agent_chat_stream` 录一组特征化测试(用 `FakeLLM` 喂固定输入、断言现有输出),作为重构安全网。

## 9. CI 与工具链

- `.github/workflows/ci.yml`:在 push / PR 触发,Python 3.12,带 Postgres service 容器;步骤为安装 `requirements.txt` + `requirements-dev.txt` → `ruff check` → `ruff format --check` → `pytest`。
- `requirements-dev.txt`:`pytest`、`pytest-asyncio`、`ruff`(httpx 进生产 `requirements.txt`)。
- `scripts/test.sh`:本地一键(起/复用测试 DB → pytest);可选 `--live` 跑真 LLM 冒烟。
- `pyproject.toml`:`[tool.pytest.ini_options]`(asyncio_mode=auto、testpaths)、`[tool.ruff]`(line-length、target py312、按现有代码风格选规则,避免大面积格式 churn)。

## 10. 回归测试目录(历史 bug → 测试映射)

| 历史 bug(commit) | 现象 | 测试落点 |
|---|---|---|
| 25733dc / 7b79fa9 / 29cd3db / 8e4cdd8 | 只发开场白/"让我查一下"就停,不调工具 | `decide_turn`:intro-only → `Retry` 再 `FallbackToolCalls`;集成层验证最终有工具执行 |
| 0a34da1 / 01289fa / af37be6 | 空助手回复 / 气泡被擦 / 误报 stream-interrupted | `decide_turn`:empty → `Retry` 再 `Fail`;集成层验证不产出空气泡、不误报中断 |
| de9d52b / f749c06 | 无效 tool_call 重试死循环;tool JSON 漏进气泡 | `pi_tool_calls` 恢复 + `decide_turn` 有界重试;`pi_stream_parser`/可见文本过滤排除 tool JSON 片段 |
| 25733dc | "继续"被误判成 intro-only 而停住 | `pi_reply_heuristics.user_requests_continuation` + `decide_turn` continuation 分支 |
| 611a6e9 / f749c06 | 多轮 tool_calls 历史校验;跳过无效 slot 的 OpenAI 协议 | `pi_tool_calls` / `format_assistant_message_for_api` 单测 |
| a5d4291 | 达到 round cap 时需总结收尾而非空转 | 集成层:round-cap 触发总结 reply |

## 11. 错误处理与预算上限

- 瞬时 LLM 错 → 退避重试,耗尽 → 类型化 error 事件 + 优雅 `done`。
- 工具执行错 → 单工具 `try/except` 捕获(沿用现有),转 `tool_result` error,agent 继续。
- 取消 → 沿用 `cancel_check`(SSE 断连 / 后台 job 取消),补集成测试。
- **新增每轮预算守卫**:跟踪单次会话累计 LLM 调用次数 / 估算 token,超阈值则停止继续调工具、优雅总结收尾(与现有 `MAX_TOOL_ROUNDS=12` 并存,作为成本兜底)。阈值可配置,默认保守。

## 12. 迁移策略

1. 先建测试地基(pyproject、deps、CI、`FakeLLM`、`scripts/test.sh`)—— 不动业务代码,CI 应立即可绿(此时只有少量初始测试)。
2. 对现有 `agent_chat_stream` 录特征化测试(用 `FakeLLM`)。
3. 抽离纯函数模块(`pi_stream_parser` → `pi_tool_calls` → `pi_reply_heuristics`),每抽一个补单测、保持 CI 绿。
4. 抽离 `decide_turn` 状态机并接回驱动器,补穷举单测 + 集成测试。
5. 新建 `pi_llm_client`(真流式 + 重试),切换 `agent_chat_stream` 的 LLM 调用,保留同步路径。
6. 加预算守卫、补回归测试、补真 LLM 冒烟。
7. 全程 `agent_chat.py` 留门面,调用方零改动;每步 CI 绿。

## 13. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 重构引入行为退化 | 特征化测试先行;每步小步提交、CI 绿才继续 |
| 真流式(httpx)切换是唯一真正动 transport 的改动 | 解析器纯函数 + SSE fixture 全测;保留同步路径;env-gated 真 LLM 冒烟兜底协议漂移 |
| `decide_turn` 复刻现有微妙短路逻辑时漏判 | 先录特征化测试锁定现状,再迁移;逐分支对照 |
| 测试需要 Postgres,本地/CI 环境差异 | 绝大多数测试注入 `tool_runner` 避开 DB;DB 测试用一次性库 + GH Actions service;`scripts/test.sh` 统一入口 |
| ruff 首次接入产生大面积格式 diff | ruff 配置贴合现有风格;格式化作为独立提交,与逻辑改动分离 |

## 14. 交付物

- 新模块:`app/pi_decisions.py`、`app/pi_reply_heuristics.py`、`app/pi_tool_calls.py`、`app/pi_stream_parser.py`、`app/pi_llm_client.py`。(`pi_tools.py` / `pi_events.py` 本子项目内延后,见 §4 说明。)
- 瘦身后的 `app/agent_chat.py`(驱动 + 门面);委托改造后的 `app/llm.py`。
- `tests/`(含 `FakeLLM`、四层测试)、`pyproject.toml`、`requirements-dev.txt`、`requirements.txt`(+httpx)、`.github/workflows/ci.yml`、`scripts/test.sh`。
