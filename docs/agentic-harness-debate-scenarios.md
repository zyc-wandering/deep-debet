# Agentic Harness: Debate Project Scenarios

## Overview

本文档将 [agentic-harness-architecture.md](./agentic-harness-architecture.md) 和 [agentic-harness-technical-design.md](./agentic-harness-technical-design.md) 中定义的通用 harness 架构，映射到 DebateAI Room 项目的具体场景。

文档涵盖：被测系统组件清单、故障模式目录、验证场景分层、debate 专属的 failure bundle 扩展、validator 工具特化、证据采集策略和实施优先级。

---

## System Under Test

### Backend Components

| 组件 | 文件路径 | 职责 |
|---|---|---|
| DebateOrchestrator | `backend/app/orchestrator.py` | 辩论生命周期编排，三阶段流程（start → configure → confirm） |
| HostAgent | `backend/app/agents/host_agent.py` | 话题研究、辩手配置生成、辩论总结、follow-up 回答 |
| DebaterAgent | `backend/app/agents/debater_agent.py` | 辩手发言生成，含上下文管理和搜索引用 |
| ContextManager | `backend/app/agents/context_manager.py` | 滚动摘要和上下文窗口构建 |
| TurnExecutor | `backend/app/execution/turn_executor.py` | 单次发言执行，含计时和流式输出 |
| OpeningStageExecutor | `backend/app/stage/opening_stage.py` | 开场陈述阶段 |
| FreeDebateStageExecutor | `backend/app/stage/free_debate_stage.py` | 自由辩论阶段（多轮对抗） |
| ClosingStageExecutor | `backend/app/stage/closing_stage.py` | 总结陈述阶段 |
| SummaryStageExecutor | `backend/app/stage/summary_stage.py` | 主持人总结和报告生成 |
| LLMProvider | `backend/app/providers/llm_openai_compat.py` | OpenAI 兼容 LLM 调用，含流式输出 |
| SearchProvider | `backend/app/providers/search_tavily.py` | Tavily 搜索集成 |
| ImageGenerationService | `backend/app/providers/image_generation.py` | 头像和背景图生成 |
| SessionStore | `backend/app/storage/session_store.py` | 内存 session 管理 + 文件持久化 |
| ReportWriter | `backend/app/storage/report_writer.py` | Markdown 报告写入 |

### Frontend Components

| 组件 | 文件路径 | 职责 |
|---|---|---|
| useDebate | `frontend/src/hooks/useDebate.ts` | SSE 流式连接管理（start/configure/confirm） |
| useFollowUp | `frontend/src/hooks/useFollowUp.ts` | Follow-up 问答流式连接 |
| debateStore | `frontend/src/store/debateStore.ts` | Zustand 状态管理（含 sessionStorage 持久化） |
| ConfigPhase | `frontend/src/components/ConfigPhase.tsx` | 话题输入和初始配置 |
| ResearchPhase | `frontend/src/components/ResearchPhase.tsx` | 研究展示和焦点选择 |
| DraftingPhase | `frontend/src/components/DraftingPhase.tsx` | 辩手阵容确认和替换 |
| ArenaPhase | `frontend/src/components/ArenaPhase.tsx` | 实时辩论展示（三面板布局） |
| SummaryPhase | `frontend/src/components/SummaryPhase.tsx` | 报告展示和 follow-up 问答 |

### SSE Event Protocol

| 事件类型 | 来源阶段 | 关键字段 | Criticality |
|---|---|---|---|
| `phase` | 全阶段 | session_id, phase, title, description | High — UI 阶段切换依赖 |
| `host_research` | start | session_id, chunk | Medium — 研究展示 |
| `focus_options_ready` | start | session_id, focus_options[] | High — 触发用户选择 |
| `debaters_ready` | configure | session_id, debaters[], main_count, deadline_at | High — 辩手配置 |
| `avatars_ready` | configure | session_id, avatars{} | Low — 头像装饰 |
| `stage_change` | confirm | session_id, stage, stage_name | High — 阶段流转 |
| `debate_turn_start` | confirm | session_id, speaker, turn_id, stage | Medium — 发言准备提示 |
| `debate_token` | confirm | session_id, speaker, turn_id, token, stage | High — 实时流式内容 |
| `debate_turn_end` | confirm | session_id, speaker, turn_id, full_content, citations, stage | High — 完整发言记录 |
| `host_summary` | confirm | session_id, chunk | Medium — 总结流式输出 |
| `structured_report` | confirm | session_id, report{} | High — 结构化分析结果 |
| `done` | confirm | session_id, report_path, total_turns, duration_sec | High — 辩论完成信号 |
| `error` | 全阶段 | session_id, message | Critical — 错误传播 |
| `follow_up_token` | followup | session_id, speaker, token | Medium — follow-up 流式 |
| `follow_up_end` | followup | session_id, speaker, full_content | Medium — follow-up 完成 |

---

## Failure Mode Catalog

### FM-01: LLM Provider Timeout

- **来源**：`llm_openai_compat.py` — httpx timeout 配置 `connect=30s, read=180s, write=30s`
- **影响**：当前阶段中断，session 转入 error 状态
- **当前处理**：httpx 超时异常冒泡到 orchestrator，session 置为 error，向前端发送 error 事件
- **Harness 检测**：监控 LLM 请求延迟分布；断言单次请求 < 180s；检测超时后 error 事件是否在 5s 内到达前端
- **证据采集**：LLM 请求时间戳、timeout 配置、error 事件内容

### FM-02: LLM Content Filter Rejection

- **来源**：`llm_openai_compat.py` — HTTP 400 + "contentFilter" → `ContentFilterError`
- **影响**：话题被拒，辩论无法进行
- **当前处理**：orchestrator 捕获 ContentFilterError，session 置为 error，发送 error 事件
- **Harness 检测**：用已知敏感话题触发，验证 error 事件包含可理解的用户提示而非原始错误码
- **证据采集**：触发话题内容、LLM 返回的 error code、前端展示的错误消息

### FM-03: LLM Empty Response

- **来源**：`debater_agent.py` — 流式响应内容为空时 raise `ValueError`
- **影响**：当前 turn 丢失，session 转入 error
- **当前处理**：ValueError 冒泡到 orchestrator
- **Harness 检测**：断言每个 `debate_turn_end` 的 `full_content` 非空；监控空响应频率
- **证据采集**：LLM 请求 prompt、空响应的 HTTP 状态码、上下文窗口大小

### FM-04: Host Agent JSON Parse Failure

- **来源**：`host_agent.py` — `_chat_json_array()` / `_chat_json_object()` 解析失败触发 repair-retry
- **影响**：配置阶段延迟，极端情况可无限循环（代码中无显式重试上限）
- **当前处理**：解析失败后 re-prompt LLM 修复 JSON，但无 max attempt 限制
- **Harness 检测**：监控 JSON repair 重试次数；设置断言上限（例如 ≤ 3 次）；检测 configure 阶段总耗时
- **证据采集**：原始 LLM 输出、repair prompt、每次重试的响应、重试次数和耗时

### FM-05: Search Provider Down

- **来源**：`search_tavily.py` — HTTP 错误或 API key 缺失
- **影响**：辩论继续但无引用，降级运行
- **当前处理**：每次搜索调用独立 try/except，失败返回空列表 `[]`
- **Harness 检测**：监控 `debate_turn_end` 中 `citations` 的空值率；搜索 API 可达性探测
- **证据采集**：搜索请求 URL、HTTP 状态码、搜索耗时、辩论中引用率统计

### FM-06: Image Generation Failure

- **来源**：`image_generation.py` — API 调用或下载失败
- **影响**：头像降级为首字母缩写，纯装饰性影响
- **当前处理**：所有失败路径返回 `None`，不阻塞辩论流程
- **Harness 检测**：检查 `avatars_ready` 事件中 avatar_url 为空的比例；前端 Avatar 组件 fallback 是否正确渲染
- **证据采集**：图片 API 请求/响应、下载 URL、前端 Avatar 渲染截图

### FM-07: SSE Stream Break

- **来源**：`useDebate.ts` — `@microsoft/fetch-event-source` 连接中断
- **影响**：前端与后端失联，用户看到辩论停滞
- **当前处理**：onerror 回调直接 throw 阻止自动重连（one-shot 设计），设置 store error 状态
- **Harness 检测**：SSE 事件序列完整性校验（必须以 `done` 或 `error` 结尾）；模拟网络中断后检查前端状态
- **证据采集**：完整 SSE 事件日志、中断时间点、前端 store 状态快照、浏览器 console 日志

### FM-08: Stop Request Latency

- **来源**：`free_debate_stage.py` — 每 20 个 token 检查一次 `session.stop_requested`
- **影响**：用户点击停止后，最多延迟 20 个 token 才响应
- **当前处理**：cooperative cancellation，opening/closing 阶段仅在辩手之间检查（不在 mid-turn 检查）
- **Harness 检测**：发送 stop 请求后计时，断言实际停止 < 10s；统计 stop 后多余的 token 数量
- **证据采集**：stop 请求时间戳、最后一个 debate_token 时间戳、stop 后收到的 token 数量

### FM-09: Deadline Enforcement Gap

- **来源**：`orchestrator.py` — deadline 仅在阶段边界和 free debate 每 20 token 检查
- **影响**：opening/closing 阶段 mid-turn 不检查 deadline，summary 阶段完全不检查
- **当前处理**：deadline 过后的当前 turn 会完整执行，summary 始终运行
- **Harness 检测**：设置短 deadline（如 30s），断言辩论总时长不超过 deadline + 合理容忍值（如 60s）
- **证据采集**：deadline 设置值、实际辩论时长、各阶段起止时间戳、deadline 过后继续执行的时间

### FM-10: Session State Race Condition

- **来源**：`session_store.py` — 内存 dict 存储，无锁
- **影响**：并发 stop + confirm 可能导致状态不一致
- **当前处理**：无显式并发控制
- **Harness 检测**：并发发送 stop 和 confirm 请求，检查 session 最终状态一致性；检查 session.json 与内存状态是否匹配
- **证据采集**：并发请求时间戳、session 状态变更日志、session.json 内容

### FM-11: Frontend Session ID Race

- **来源**：`debateStore.ts` — `setSessionId` 使用 `s.sessionId ||` 语义（first-wins）
- **影响**：如果第一个事件携带错误 session_id，后续正确 ID 被忽略
- **当前处理**：仅接受第一个到达的 session_id
- **Harness 检测**：校验前端 store 中的 sessionId 与后端 session 一致；监控同一 SSE 流中是否出现多个不同 session_id
- **证据采集**：SSE 事件中的 session_id 序列、前端 store 状态、后端 session 状态

### FM-12: Frontend Token/Turn Finalization Race

- **来源**：`debateStore.ts` — `appendToken` 和 `finalizeTurn` 的调用顺序
- **影响**：transcript 中可能出现乱序或重复条目
- **当前处理**：无排序保证，依赖事件到达顺序
- **Harness 检测**：对比后端 session.messages 顺序与前端 transcript 顺序；检查 turn_id 单调递增
- **证据采集**：后端消息列表、前端 transcript 列表、SSE 事件时间戳序列

---

## Scenario Tiers

### Tier 1: Smoke

快速可达性验证，每次部署必跑。

| Scenario ID | 描述 | 前置条件 | 关键断言 | 目标 FM | 预计耗时 | 建议频率 |
|---|---|---|---|---|---|---|
| `smoke-health` | `/api/health` 返回 200 | 后端启动 | status=ok, 包含 feature flags | — | < 5s | 每次部署 + 每 5min |
| `smoke-openapi` | `/openapi.json` 包含所有端点 | 后端启动 | 包含 /api/debate/start, /api/debate/configure, /api/debate/confirm | — | < 5s | 每次部署 |
| `smoke-start-sse` | `POST /api/debate/start` 建立 SSE 连接并收到首个 phase 事件 | 后端启动 + LLM 可达 | 收到 `phase` 事件，session_id 非空 | FM-07 | < 30s | 每次部署 |
| `smoke-frontend` | 前端页面加载，ConfigPhase 渲染，无 JS 错误 | 前端构建完成 | 页面加载 < 3s，console 无 error，topic input 可见 | — | < 10s | 每次部署 |

### Tier 2: Business E2E

核心业务流程端到端验证。

| Scenario ID | 描述 | 前置条件 | 关键断言 | 目标 FM | 预计耗时 | 建议频率 |
|---|---|---|---|---|---|---|
| `e2e-happy-path` | 完整辩论流程：输入话题 → 研究 → 选焦点 → 确认辩手 → 辩论 → 总结 → 报告 | 全服务可用 | 收到 done 事件，report_path 非空，报告文件可读取，structured_report 包含 host_conclusion | FM-01~06 | 3-8min | 每次部署 |
| `e2e-stop-interrupt` | 辩论进行中点击停止 | 进入 free_debate 阶段 | stop 后 < 10s 收到 done 事件，transcript 中已完成的 turn 完整 | FM-08 | 1-3min | 每次部署 |
| `e2e-follow-up` | 辩论完成后向特定辩手提问 | 辩论已完成 | 收到 follow_up_end 事件，full_content 非空且与辩手立场一致 | — | 30s-1min | 每日 |
| `e2e-debater-swap` | 在 drafting 阶段替换辩手后开始辩论 | 进入 drafting 阶段 | 替换后的辩手出现在辩论中，原辩手不再发言 | — | 3-8min | 每日 |
| `e2e-sse-ordering` | 验证 SSE 事件严格有序 | 全服务可用 | phase 事件按预期顺序到达，turn_id 单调递增，每个 turn_start 后必有对应 turn_end | FM-07, FM-12 | 3-8min | 每次部署 |
| `e2e-structured-report` | 验证结构化报告完整性 | 辩论完成 | structured_report 包含 background_summary、core_arguments、clash_points、host_conclusion，host_conclusion 包含 winning_argument + strongest_debater + ≥2 reasons | FM-04 | 3-8min | 每次部署 |
| `e2e-session-persist` | 页面刷新后 session 状态恢复 | 辩论进行中 | 刷新后 sessionId 不变，transcript 与刷新前一致，phase 正确恢复 | FM-10, FM-11 | 2-5min | 每日 |

### Tier 3: External Probes

第三方依赖可达性探测。

| Scenario ID | 描述 | 前置条件 | 关键断言 | 目标 FM | 预计耗时 | 建议频率 |
|---|---|---|---|---|---|---|
| `probe-llm` | LLM API 可达性和基础功能 | API key 配置 | 简单 prompt 返回非空响应，延迟 < 30s | FM-01, FM-02 | < 30s | 每 15min |
| `probe-search` | Tavily 搜索 API 可达性 | API key 配置 | 搜索返回 ≥ 1 结果，延迟 < 10s | FM-05 | < 15s | 每 30min |
| `probe-image` | 图片生成 API 可达性 | API key 配置 | 生成请求返回有效 URL，图片可下载 | FM-06 | < 30s | 每小时 |

### Tier 4: Resilience

故障注入和边界测试。

| Scenario ID | 描述 | 前置条件 | 关键断言 | 目标 FM | 预计耗时 | 建议频率 |
|---|---|---|---|---|---|---|
| `res-llm-degraded` | LLM 响应延迟注入（模拟慢响应） | mock/proxy 可用 | 辩论仍能完成或超时后优雅降级，error 事件包含有意义信息 | FM-01 | 5-10min | 每周 |
| `res-content-filter` | 使用已知触发 content filter 的话题 | LLM 可达 | 收到 error 事件且 message 对用户友好，session 状态为 error | FM-02 | < 1min | 每周 |
| `res-search-down` | 搜索服务不可达时的降级行为 | 搜索 API key 无效或不可达 | 辩论正常完成，debate_turn_end 中 citations 为空数组，无 error 事件 | FM-05 | 3-8min | 每周 |
| `res-image-down` | 图片服务不可达时的降级行为 | 图片 API 不可达 | debaters_ready 正常发送，avatar_url 为 null，前端显示首字母 fallback | FM-06 | 2-5min | 每周 |
| `res-long-debate` | 最大辩手数 + 最大轮次压力测试 | 全服务可用 | 辩论完成不 OOM，上下文窗口管理正常，report 可生成 | FM-04, FM-09 | 15-30min | 每周 |
| `res-concurrent` | 3 个并发辩论 session | 全服务可用 | 所有 session 独立完成，无状态串扰，session_id 严格隔离 | FM-10 | 10-20min | 每周 |
| `res-deadline-overrun` | 短 deadline（30s）下的超时处理 | 全服务可用 | 总时长 < deadline + 60s，summary 仍然生成 | FM-09 | 1-2min | 每日 |
| `res-session-reload` | 辩论中途刷新页面后恢复 | 进入 arena 阶段 | 刷新后 transcript 完整，可通过 /api/sessions/{id} 恢复状态 | FM-10, FM-11, FM-12 | 3-5min | 每日 |

---

## Debate-Specific Failure Bundle Schema

在通用 failure bundle（参见 [architecture doc - Failure Bundle Contract](./agentic-harness-architecture.md#failure-bundle-contract)）基础上，增加 debate 专属字段：

```json
{
  "workflow_run_id": "wr_20260329_001",
  "scenario_id": "e2e-happy-path",
  "trigger_type": "ci_deploy",
  "git_sha": "8469659",
  "environment": "staging",
  "validator_summary": "Structured report missing host_conclusion.reasoning field after full debate completion.",
  "confidence": 0.92,

  "debate_context": {
    "session_id": "sess_abc123",
    "topic": "AI 是否应该拥有法律人格",
    "language": "zh",
    "model_variant": "lite",
    "debater_count": 4,
    "max_turns": 6,
    "time_limit_sec": 300,
    "web_search_enabled": true,
    "selected_focus_id": "focus_02"
  },

  "expected_result": "structured_report.host_conclusion should contain winning_argument, strongest_debater, and at least 2 reasoning items.",
  "actual_result": "host_conclusion.reasoning is an empty array.",

  "attachments": {
    "sse_event_log": "artifacts/sse_events.jsonl",
    "llm_request_response_pairs": "artifacts/llm_pairs.jsonl",
    "search_query_results": "artifacts/search_results.jsonl",
    "session_state_before": "artifacts/session_before.json",
    "session_state_after": "artifacts/session_after.json",
    "frontend_store_diff": "artifacts/store_diff.json",
    "screenshots": [
      "artifacts/summary-phase-missing-conclusion.png"
    ],
    "browser_console": "artifacts/browser-console.log",
    "network_har": "artifacts/network.har"
  }
}
```

### 附件格式说明

| 附件 | 格式 | 说明 |
|---|---|---|
| `sse_events.jsonl` | JSON Lines | 每行一个 SSE 事件：`{timestamp, event_type, data, _trace}` |
| `llm_pairs.jsonl` | JSON Lines | 每行一次 LLM 调用：`{timestamp, method, model, messages_hash, prompt_tokens, completion_tokens, duration_ms, response_preview}`。`messages_hash` 避免存储完整 prompt，response_preview 截取前 500 字符 |
| `search_results.jsonl` | JSON Lines | 每行一次搜索：`{timestamp, query, provider, result_count, duration_ms, results_preview}` |
| `session_before/after.json` | JSON | 完整 session 状态快照（脱敏后），before 在场景开始时采集，after 在失败时采集 |
| `store_diff.json` | JSON | 前端 Zustand store 的 diff（通过 Playwright evaluate 提取），包含 phase、sessionId、lines 数量、errorMessage 等关键字段 |

---

## Validator Tool Specializations

在通用 validator 工具集（参见 [technical design doc - Validator Tool Set](./agentic-harness-technical-design.md#validator-tool-set)）基础上，增加 debate 专属工具：

### sse_event_recorder

记录完整 SSE 事件流到 JSONL 文件。

- **输入**：SSE endpoint URL, request body, timeout
- **输出**：`sse_events.jsonl` artifact
- **实现**：基于 httpx SSE 客户端，逐事件追加写入，包含精确时间戳
- **注意**：后端已有 `_trace` 字段随事件下发，recorder 应保留该字段

### sse_sequence_validator

校验 SSE 事件序列的正确性。

- **输入**：`sse_events.jsonl` 文件路径
- **输出**：验证结果（pass/fail + 违规详情）
- **校验规则**：
  - `phase` 事件按预期顺序：booting → researching → configuring → assembling → drafting → opening → free_debate → closing → summarizing
  - 每个 `debate_turn_start` 必有对应的 `debate_turn_end`（相同 speaker + turn_id）
  - `turn_id` 在同一 stage 内单调递增
  - 流必须以 `done` 或 `error` 结尾
  - `focus_options_ready` 中 options 数量 ≥ 2
  - `debaters_ready` 中 debaters 数量 ≥ 2

### llm_call_interceptor

通过 HTTP proxy 或 monkey-patch 捕获所有 LLM 请求/响应对。

- **输入**：proxy 配置或 patch target
- **输出**：`llm_pairs.jsonl` artifact
- **实现建议**：在 sandbox 中启动轻量 HTTP proxy（如 mitmproxy addon），拦截发往 LLM base_url 的请求
- **脱敏**：不存储完整 prompt（可能包含用户输入），仅存储 hash + token 计数 + 响应预览

### search_call_interceptor

捕获所有搜索 API 请求和结果。

- **输入**：proxy 配置或 patch target
- **输出**：`search_results.jsonl` artifact
- **实现**：与 llm_call_interceptor 共享 proxy 基础设施

### session_state_snapshotter

在关键节点采集后端 session 状态快照。

- **输入**：session_id, snapshot_label（如 "before_free_debate", "after_stop"）
- **输出**：`session_{label}.json` artifact
- **实现**：通过 `/api/sessions/{session_id}` 端点读取，或直接读取 `{debate_dir}/session.json` 文件
- **采集时机**：场景开始前、每个 stage 切换后、失败检测后

### frontend_store_extractor

通过 Playwright 提取前端 Zustand store 的当前状态。

- **输入**：Playwright page 对象
- **输出**：store 关键字段 JSON
- **实现**：`page.evaluate(() => window.__ZUSTAND_STORE__.getState())` 或通过 devtools hook
- **提取字段**：phase, status, sessionId, errorMessage, lines.length, transcript.length, currentStage, activeSpeaker, liveBuffers keys
- **注意**：需在前端构建时暴露 store reference（仅在 test/staging 环境）

### debate_flow_asserter

端到端流程断言工具，组合使用上述工具的输出进行综合判断。

- **输入**：scenario 配置（预期 debater_count, max_turns, 预期阶段序列等）
- **输出**：断言结果（pass/fail + 每条断言的详情）
- **核心断言**：
  - Phase 转换完整且有序
  - 每位辩手的 turn 数量符合预期
  - report_path 指向的文件存在且非空
  - structured_report 各必需字段非空
  - 前端 transcript 条目数 == 后端 session.messages 数
  - 辩论总时长在合理范围内

---

## Evidence Collection Strategy

### 采集时机矩阵

| 采集点 | sse_event_log | llm_pairs | search_results | session_state | frontend_store | screenshot | HAR |
|---|---|---|---|---|---|---|---|
| 场景开始 | 开始录制 | 开始录制 | 开始录制 | 采集 before | 采集 before | — | 开始录制 |
| 每次 stage_change | — | — | — | 采集 | 采集 | 可选 | — |
| 失败检测 | 停止录制 | 停止录制 | 停止录制 | 采集 after | 采集 after | 截图 | 停止录制 |
| 场景完成（成功） | 停止录制 | 停止录制 | 停止录制 | 采集 after | — | — | 停止录制 |

### 存储路径

```text
runs/{workflow_run_id}/{scenario_id}/
  sse_events.jsonl
  llm_pairs.jsonl
  search_results.jsonl
  session_before.json
  session_after.json
  session_stage_{stage_name}.json    (per stage)
  store_before.json
  store_after.json
  store_stage_{stage_name}.json      (per stage, optional)
  screenshots/
    failure.png
    stage_{stage_name}.png           (optional)
  network.har
  browser-console.log
  failure_bundle.json
```

### 大小控制

- `sse_events.jsonl`：不截断，完整记录（典型大小 < 1MB）
- `llm_pairs.jsonl`：response_preview 限制 500 字符，prompt 仅存 hash
- `search_results.jsonl`：results_preview 限制每条 200 字符
- `session_*.json`：完整存储（典型大小 < 500KB）
- `screenshots`：PNG 格式，1280x720 分辨率
- `network.har`：保留 SSE 和 API 请求，过滤静态资源

---

## Cross-Reference Map

| 本文档章节 | 架构文档对应章节 | 技术设计文档对应章节 |
|---|---|---|
| SSE Event Protocol | — | — |
| Failure Mode Catalog | Failure Bundle Contract | LangGraph Design |
| Scenario Tiers | Test Scope Strategy | GitHub Actions Pipeline Design |
| Failure Bundle Schema | Failure Bundle Contract | Artifact Service |
| Validator Tool Specializations | — | Validator Tool Set / Tooling Model |
| Evidence Collection Strategy | — | Artifact Service |
| Implementation Priority | Rollout Plan | Rollout Recommendation |

---

## Implementation Priority

### Phase 1: Foundation（Week 1-2）

**目标**：打通 Tier 1 Smoke 和核心工具链。

- 实现 `sse_event_recorder` 和 `sse_sequence_validator`
- 实现 `debate_flow_asserter` 的基础版本（phase 序列 + done/error 断言）
- 完成 4 个 Smoke 场景
- 搭建 artifact 存储目录结构
- 输出：可在本地手动运行的 validator 原型

### Phase 2: Core Coverage（Week 3-4）

**目标**：覆盖 Tier 2 Business E2E 核心场景。

- 实现 `llm_call_interceptor` 和 `search_call_interceptor`
- 实现 `session_state_snapshotter`
- 完成 `e2e-happy-path`、`e2e-stop-interrupt`、`e2e-sse-ordering`、`e2e-structured-report` 四个高优先级场景
- 集成 failure bundle 生成
- 输出：CI 可运行的 E2E 验证套件

### Phase 3: Resilience（Week 5-6）

**目标**：覆盖 Tier 3-4 和完整前端验证。

- 实现 `frontend_store_extractor`（需前端 test build 支持）
- 完成 3 个 External Probe 场景
- 完成高优先级 Resilience 场景：`res-search-down`、`res-image-down`、`res-deadline-overrun`、`res-session-reload`
- 完善 `debate_flow_asserter` 的断言覆盖
- 输出：完整的验证场景库 + failure bundle 全链路

### Phase 4: Automation（Week 7-8）

**目标**：接入 GitHub Actions 和 auto-triage。

- 配置 GitHub Actions workflow：deploy 后触发 Tier 1-2，scheduled 触发 Tier 3
- 实现 failure bundle → GitHub issue 自动创建
- 配置 auto-triage criteria（参见 [architecture doc - Auto-triage Criteria](./agentic-harness-architecture.md#auto-triage-criteria)）
- 搭建结果看板（Grafana 或 GitHub Actions dashboard）
- 剩余 Resilience 场景补全
- 输出：全自动验证 + 人工审批闭环
