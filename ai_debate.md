<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# DebateAI — 落地实施计划

***

## 一、产品核心定义

**一句话定位**：用户输入任意话题，AI 自动召集多个具有独立人设的辩手 Agent，在限定时间内展开真实辩论，最终输出一份多视角深度调研报告保存至本地。

**核心价值**：

- 批判性多视角：强迫 AI 输出对立观点，而非中庸结论
- 信息广度：主持人先做网络调研，辩论基于真实当前信息
- 成果沉淀：Markdown 报告本地永久保存

***

## 二、完整系统流程

```
用户输入话题 + 选择参数（辩手数量、时间限制）
        ↓
[阶段 1] 准备阶段 ── 主持人 Agent
  web_search(topic)         → 获取背景信息
  create_brief()            → 生成话题调研简报
  create_debater(x N)       → 创建 2~5 个辩手实例（人设 + 立场）
  init_debate()             → 初始化辩论室，分发简报给所有辩手
        ↓
[阶段 2] 辩论阶段 ── N 个 Debater Agent 轮流
  每个辩手每轮：
    web_search(sub_query)   → 可选，补充实时论据
    speak(content)          → 发言到辩论室（流式推送至前端）
  Orchestrator 管理轮次，检查时间阈值
        ↓
[阶段 3] 总结阶段 ── 主持人 Agent
  web_search(follow_up)     → 可选，补充遗漏信息
  finish_debate(debate_log) → 生成结构化报告 + 保存本地
        ↓
用户收到 Markdown 报告，会话结束
```


***

## 三、Agent 工具设计详解

### 3.1 主持人 Agent（Host Agent）

主持人拥有全局视野，负责辩论生命周期的完整管理。

#### 工具清单

| 工具名 | 入参 | 出参 | 说明 |
| :-- | :-- | :-- | :-- |
| `web_search` | `query: str, num_results: int = 5` | `List[SearchResult]` | 调研话题背景，支持多次调用 |
| `create_debater` | `name: str, background: str, stance: str, personality: str` | `DebaterConfig` | 创建单个辩手人设，可调用 2~5 次 |
| `init_debate` | `topic: str, brief: str, debaters: List[DebaterConfig], time_limit_sec: int` | `DebateSession` | 初始化辩论室，分发简报，建立 debate_log，启动计时器 |
| `finish_debate` | `debate_log: List[Message], brief: str` | `ReportPath` | 汇总所有发言，生成 Markdown 报告，写入本地文件 |

#### 主持人 System Prompt 设计

```
你是一位专业的辩论主持人和研究员。
你的任务分为两个阶段：

【准备阶段】
1. 使用 web_search 对用户给定话题进行深度调研（至少 2~3 次搜索）
2. 整理成一份客观的背景简报 Brief（500~800字）
3. 根据话题，使用 create_debater 工具创建 {N} 个立场鲜明、人设差异大的辩手
   - 辩手人设需涵盖不同价值观维度（技术派/人文派/政策派/商业派/怀疑派等）
4. 调用 init_debate 正式启动辩论室

【总结阶段】
当收到辩论结束信号后：
1. 可选择使用 web_search 补充遗漏信息
2. 调用 finish_debate 生成报告，报告需包含：
   - 话题背景与调研摘要
   - 各辩手核心论点与代表性发言
   - 多方观点的综合评述
   - 主持人的综合结论
```


***

### 3.2 辩手 Agent（Debater Agent）

每个辩手是独立实例，拥有独立 system prompt、独立上下文窗口，彼此不共享历史。

#### 工具清单

| 工具名 | 入参 | 出参 | 说明 |
| :-- | :-- | :-- | :-- |
| `web_search` | `query: str, num_results: int = 3` | `List[SearchResult]` | 搜索支撑自己论点的实时论据，每轮可选用 |
| `speak` | `content: str` | `SpeakAck` | 将发言内容写入辩论室 debate_log，并通过 SSE 流式推送至前端 |

#### 辩手 System Prompt 模板

```
你是 {name}，{background}。

你的辩论立场：{stance}
你的性格与风格：{personality}

你正在参与一场关于「{topic}」的多方辩论。
辩论开始前，主持人已为你准备了以下背景简报：
---
{brief}
---

轮到你发言时，你需要：
1. 仔细阅读场上已有的发言记录（尤其是最近 10 轮）
2. 可以选择使用 web_search 搜索实时资料来增强你的论点
3. 调用 speak 工具发表你的观点，要求：
   - 鲜明体现你的立场与人设
   - 可以针对其他辩手的论点进行反驳或追问
   - 每次发言控制在 150~300 字
   - 语言风格应符合你的角色设定
```


***

### 3.3 工具实现设计

#### `web_search` 工具（共用）

```python
async def web_search(query: str, num_results: int = 5) -> List[SearchResult]:
    """
    封装 Tavily API / Serper API
    返回结构：[{title, url, snippet, published_date}]
    Host 调用：调研简报生成
    Debater 调用：寻找实时论据，每轮限制最多 1 次，避免延迟过高
    """
```


#### `speak` 工具（辩手专属）

```python
async def speak(content: str) -> SpeakAck:
    """
    1. 将发言追加至全局 debate_log
    2. 通过 SSE 队列推送 {speaker_name, content, timestamp} 至前端
    3. 触发前端对应辩手卡片的流式渲染
    4. 返回发言 ID 确认
    """
```


#### `create_debater` 工具（主持人专属）

```python
async def create_debater(
    name: str,
    background: str,
    stance: str,
    personality: str
) -> DebaterConfig:
    """
    实例化一个 DebaterAgent 对象：
    - 注入个性化 system prompt
    - 初始化独立的消息历史列表
    - 注册 web_search + speak 工具
    - 返回 DebaterConfig（含 agent 实例引用）
    """
```


#### `init_debate` 工具（主持人专属）

```python
async def init_debate(
    topic: str,
    brief: str,
    debaters: List[DebaterConfig],
    time_limit_sec: int
) -> DebateSession:
    """
    1. 创建全局 DebateSession（含 debate_log、计时器、状态机）
    2. 向所有辩手分发 Brief（写入各自初始上下文）
    3. 通过 SSE 推送 'debaters_ready' 事件至前端（触发角色卡展示）
    4. 启动计时器
    5. 返回 session_id，Orchestrator 开始轮询驱动辩论
    """
```


#### `finish_debate` 工具（主持人专属）

```python
async def finish_debate(
    debate_log: List[Message],
    brief: str
) -> ReportPath:
    """
    1. 将完整 debate_log + brief 送入主持人 LLM 生成报告
    2. 报告格式：Markdown，包含摘要/各方论点/综合结论
    3. 文件名：{topic_slug}_{timestamp}.md
    4. 写入本地 ~/DebateAI/reports/ 目录
    5. 通过 SSE 推送 'done' 事件，携带文件路径
    """
```


***

## 四、上下文窗口管理策略

辩论核心挑战在于上下文长度控制，每个辩手的输入按以下优先级组装：

```
┌─────────────────────────────────────────┐
│  1. System Prompt + 人设（固定，~300 tokens）  │
├─────────────────────────────────────────┤
│  2. Brief Document（固定，~800 tokens）        │
├─────────────────────────────────────────┤
│  3. Rolling Summary（每5轮更新一次，~400 tokens）│
│     ← 超过10轮的早期发言会被压缩进这里            │
├─────────────────────────────────────────┤
│  4. 最近 10 轮完整发言（动态，~2000 tokens）      │
├─────────────────────────────────────────┤
│  5. 当前轮次指令（固定，~100 tokens）             │
└─────────────────────────────────────────┘
总预算上限：~4000 tokens（输入）
```

**Rolling Summary 更新逻辑**：每完成 5 轮辩论，Orchestrator 调用一次轻量 LLM 请求，把第 1~N-10 轮的发言压缩为滚动摘要，下一轮辩手的上下文用新摘要替换旧的早期记录。

***

## 五、技术架构

### 完整分层架构图

```
┌──────────────────────────────────────────────────┐
│              Frontend（React + TypeScript）         │
│                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ 话题输入页   │  │ 辩论实时流   │  │ 报告展示 │  │
│  │ + 参数选择   │  │ DebateStream │  │ Markdown │  │
│  └─────────────┘  └──────────────┘  └──────────┘  │
│       SSE Consumer（@microsoft/fetch-event-source） │
└────────────────────┬─────────────────────────────┘
                     │ POST /debate/start（SSE Stream）
┌────────────────────▼─────────────────────────────┐
│              Backend（FastAPI + Python）            │
│                                                    │
│  /debate/start → StreamingResponse（SSE）           │
│  /debate/stop  → 中止当前 session                  │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│           Agent Orchestrator Layer                 │
│                                                    │
│  DebateOrchestrator（async while-loop驱动）         │
│  ├── HostAgent                                     │
│  │   ├── Tool: web_search                          │
│  │   ├── Tool: create_debater                      │
│  │   ├── Tool: init_debate                         │
│  │   └── Tool: finish_debate                       │
│  ├── DebaterAgent[0]                               │
│  │   ├── Tool: web_search                          │
│  │   └── Tool: speak ──→ SSE Queue                 │
│  ├── DebaterAgent[1..N]（同上）                     │
│  └── ContextManager（滑动窗口 + Rolling Summary）   │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│               Infrastructure Layer                 │
│  Tavily/Serper API（Web Search）                   │
│  OpenAI / Anthropic API（LLM）                     │
│  Local FileSystem（报告存储）                       │
│  In-Memory Dict / Redis（Session 状态）             │
└──────────────────────────────────────────────────┘
```


### 技术栈一览

| 层 | 选型 | 理由 |
| :-- | :-- | :-- |
| 前端框架 | React 18 + TypeScript | 组件化管理多辩手并发渲染 |
| SSE 客户端 | `@microsoft/fetch-event-source` | 支持 POST body + 自动重连，原生 EventSource 不支持 POST |
| 前端状态 | Zustand | 轻量异步友好，管理 session / debater / log 状态 |
| Markdown 渲染 | `react-markdown` + `remark-gfm` | 实时渲染发言和报告 |
| 后端框架 | FastAPI (Python) | 原生 `StreamingResponse` 支持 SSE，async 生态完善 |
| Agent 框架 | Pydantic AI | 类型安全、原生多 Agent 委派、工具绑定清晰 |
| Agent Loop | nano agentloop 范式（while + tool-call） | 轻量可控，避免框架黑盒 |
| Web Search | Tavily API | 专为 LLM 设计，返回结构化 snippet，支持时效性过滤 |
| LLM | Codex 5.3 主力 / GLM-5 可选降级 | 按订阅灵活切换 |
| 本地存储 | `pathlib`（文件系统） | 报告 Markdown 直接写本地，无需数据库 |


***

## 六、SSE 事件协议设计

前后端约定以下 SSE event 类型：


| Event 类型 | 触发时机 | Data 内容 |
| :-- | :-- | :-- |
| `host_research` | 主持人调研流式输出 | `{chunk: str}` |
| `debaters_ready` | `init_debate` 完成后 | `{debaters: [{name, background, stance, avatar_emoji}]}` |
| `debate_token` | 辩手每次 `speak` 调用，逐 token 推送 | `{speaker: str, token: str, turn_id: int}` |
| `debate_turn_end` | 某辩手本轮发言完毕 | `{speaker: str, full_content: str}` |
| `host_summary` | 主持人总结阶段流式输出 | `{chunk: str}` |
| `done` | `finish_debate` 完成 | `{report_path: str, total_turns: int}` |
| `error` | 任意阶段异常 | `{stage: str, message: str, retrying: bool}` |


***

## 七、项目目录结构

```
debate-ai/
├── backend/
│   ├── main.py                    # FastAPI 入口 + SSE 路由
│   ├── orchestrator.py            # DebateOrchestrator（主循环）
│   ├── agents/
│   │   ├── host_agent.py          # 主持人 Agent + 工具绑定
│   │   ├── debater_agent.py       # 辩手 Agent + 工具绑定
│   │   └── context_manager.py    # 滑动窗口 + Rolling Summary
│   ├── tools/
│   │   ├── web_search.py          # Tavily 封装
│   │   ├── speak.py               # speak 工具（写 log + 推 SSE）
│   │   ├── create_debater.py      # create_debater 工具
│   │   ├── init_debate.py         # init_debate 工具
│   │   └── finish_debate.py       # finish_debate 工具（生成 + 保存报告）
│   ├── models.py                  # Pydantic 数据模型
│   └── session_store.py           # 会话状态管理（内存 / Redis）
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   └── DebatePage.tsx     # 主页面（话题输入 + 辩论流 + 报告）
    │   ├── components/
    │   │   ├── TopicInput.tsx     # 话题输入 + 参数配置
    │   │   ├── DebaterCard.tsx    # 辩手角色卡（名字/人设/头像）
    │   │   ├── DebateStream.tsx   # 实时发言流渲染
    │   │   ├── Timer.tsx          # 倒计时进度条
    │   │   └── ReportView.tsx     # Markdown 报告展示 + 下载
    │   ├── store/
    │   │   └── debateStore.ts     # Zustand 全局状态
    │   └── hooks/
    │       └── useDebate.ts       # SSE 消费 Hook（核心逻辑）
    └── package.json
```


***

## 八、关键工程注意事项

**SSE 稳定性**

- 后端响应头必须加 `X-Accel-Buffering: no`，防止 Nginx 缓冲导致流中断
- 前端 `fetchEventSource` 配置 `openWhenHidden: true`，防止切换标签页断流

**工具调用失败处理**

- `web_search` 失败：跳过本次搜索，直接进入发言，不阻塞辩论流程
- `speak` 失败：重试最多 2 次，仍失败则跳过该辩手本轮，继续下一位
- `finish_debate` 失败：保存原始 debate_log 为 `.json` 兜底，确保数据不丢失

**辩手 `web_search` 频率控制**

- 每位辩手每轮最多调用 1 次 `web_search`，超出则被 Orchestrator 拦截
- 避免辩手无限搜索导致单轮延迟爆炸

**报告本地路径**

- 默认保存至 `~/DebateAI/reports/{topic_slug}_{yyyyMMdd_HHmmss}.md`
- 前端通过 `done` 事件拿到路径后，展示"已保存至本地"提示

***

## 九、MVP 功能边界

**MVP 必须包含（P0）**

- 话题输入 + 时间选择 + 辩手数量选择
- 主持人调研 + Brief 生成
- 自动创建辩手（人设 + 立场）
- 多辩手轮流发言（流式渲染）
- 时间到自动触发总结
- 报告生成 + 本地保存

**MVP 暂缓（P1/P2）**

- 用户手动打断辩论、提前结束
- 辩手发言时实时 web_search（MVP 可先禁用，主持人 Brief 已包含背景）
- 历史会话管理与报告列表
- 辩手头像 AI 生成
- 多语言支持

# 十，接入LLM
接入的 LLM 使用 Kimi，API key 从本地配置读取。

本地配置方式（不要提交到 Git）：
- 优先设置环境变量 `KIMI_CODE_API_KEY`
- 或在仓库根目录的 ignored 文件 `keys.ts` 中配置 `kimi_code_api_key`
