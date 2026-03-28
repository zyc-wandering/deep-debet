# Agentic Harness Technical Design

## Overview

本文档在 [agentic-harness-architecture.md](./agentic-harness-architecture.md) 的基础上继续细化，给出技术选型、核心组件设计、sandbox 设计、LangGraph agent 设计、工具权限模型以及 GitHub Actions 流水线方案。

本文档默认以下约束：

- sandbox 运行时使用 Alibaba 开源 `OpenSandbox`
- agent 编排框架使用 `LangGraph`
- sandbox 默认环境为 Linux
- CI/CD 流水线使用 `GitHub Actions`
- 工具层设计参考 Cursor 一类 coding agent 的工具哲学，但要更严格地做权限分层

## Technical Selection

### Control Plane

- Language: `Python 3.12`
- Service framework: `FastAPI`
- Background execution: `Celery` 或 `Arq`
- State store: `PostgreSQL`
- Artifact metadata store: `PostgreSQL`
- Binary artifact store: `S3-compatible object storage` 或本地 MinIO

选择理由：

- `LangGraph` 的 Python 生态成熟，与现有后端技术栈衔接自然
- 控制平面需要显式状态机、审批状态、运行日志和 artifact 索引，关系型数据库更稳
- artifact 附件体积较大，适合对象存储

### Sandbox Runtime

- Sandbox runtime: `OpenSandbox`
- Default image OS: `Ubuntu 22.04 LTS`
- Session model: 一次 workflow run 对应两个独立 sandbox session
- Network policy:
  - validator sandbox 可访问预发域名、日志网关、观测服务、必要第三方测试入口
  - coding sandbox 默认禁止外网，只允许代码仓库和内部 artifact 读取

选择理由：

- OpenSandbox 适合将 agent 执行与权限边界下沉到隔离运行时
- Linux 环境更适合统一浏览器自动化、压测、日志处理和代码工具链

### Agent Runtime

- Agent framework: `LangGraph`
- LLM provider: 可配置 OpenAI-compatible provider
- Prompt asset management: repo 内版本化 prompt + policy files
- Memory:
  - 短期 memory: 单次 workflow state
  - 长期 memory: 历史 flaky、外部依赖已知异常、项目调试约束

### Browser and Test Stack

- Browser automation: `Playwright`
- API verification: `httpx` / `pytest`
- Load probe: `k6` 或 `Locust`
- Visual diff: `Playwright screenshot + pixelmatch` 或 `Resemble.js`
- Log/trace query adapters: OpenTelemetry-compatible backend, Loki, Elasticsearch, Datadog 等通过 adapter 封装

### Git and Delivery

- CI/CD: `GitHub Actions`
- PR automation: `GitHub App` 或 `gh` CLI with bot token
- Human approval:
  - GitHub PR review
  - GitHub issue/comment approval
  - GitHub environment protection rules

## System Context

```mermaid
flowchart LR
    GH["GitHub Actions"] --> API["Harness Control Plane API"]
    API --> DB["PostgreSQL"]
    API --> OBJ["Artifact Store"]
    API --> OS["OpenSandbox Cluster"]
    API --> GHAPI["GitHub API"]

    OS --> VS["Validator Sandbox"]
    OS --> CS["Coding Sandbox"]

    VS --> PRE["Preprod / Sandbox Environment"]
    VS --> OBS["Logs / Trace / Metrics"]
    CS --> REPO["Repository Mirror / Git Clone"]
    CS --> OBJ
```

## Core Components

### 1. Harness Control Plane

这是整个系统的核心服务，建议实现为独立后端服务。

职责：

- 接收来自 GitHub Actions、QA 定时任务、手动触发的 workflow 请求
- 创建 workflow run、状态记录和审批任务
- 调用 OpenSandbox 创建 validator 和 coding sandbox
- 将 LangGraph graph 运行时注入 sandbox
- 管理 artifact 索引和访问地址
- 控制权限升级，例如将 coding sandbox 从只读提升为 fix-branch write
- 负责关闭、重试和终止 workflow

建议模块：

- `api/`
  提供 workflow 启动、审批、状态查询接口
- `services/workflows/`
  workflow 生命周期管理
- `services/sandboxes/`
  OpenSandbox session 管理
- `services/artifacts/`
  artifact metadata 和对象存储索引
- `services/github/`
  PR、comment、status check、branch 管理
- `services/policies/`
  权限、auto-fix policy、review gate 策略
- `services/memory/`
  历史 flaky 和记忆管理

### 2. OpenSandbox Manager

该模块是对 OpenSandbox 的一层适配封装，避免业务逻辑直接耦合到 runtime API。

职责：

- 根据 workflow mode 启动不同镜像模板
- 注入只读或读写 git credential
- 配置 network allowlist
- 配置 CPU、内存、磁盘和超时
- 下发工具 manifest
- 回收过期 session

建议支持两类 sandbox profile：

- `validator-linux-browser`
- `coding-linux-readonly`
- `coding-linux-fix`

其中 `coding-linux-fix` 不是长期常驻 profile，而是从只读 profile 升级或重建出的短期 profile。

### 3. Artifact Service

artifact service 负责归档 validator 和 coding agent 交互所需的所有材料。

建议 artifact 分类：

- `failure_bundle.json`
- `screenshots/*.png`
- `video/*.webm`
- `network/*.har`
- `logs/*.log`
- `trace/*.json`
- `diagnosis_report.md`
- `patch_summary.md`
- `regression_results.json`

建议对象路径格式：

`runs/{workflow_run_id}/{scenario_id}/{artifact_type}/...`

### 4. Policy Engine

policy engine 决定谁能用什么工具、能否自动进入下一阶段、哪些修复允许自动执行。

建议最小策略维度：

- `trigger_type`
  preprod、scheduled_probe、developer_self_test
- `risk_level`
  low、medium、high
- `tool_scope`
  browse、api、logs、repo_read、repo_write、git_push、pr_open
- `change_scope`
  tests_only、frontend_only、backend_only、cross_service

## LangGraph Design

## Validator Graph

validator agent 的目标不是自由探索，而是遵循受控测试计划，执行标准化流程并生成 failure bundle。

建议 graph 节点：

```mermaid
flowchart TD
    A["Load Scenario Plan"] --> B["Load Memory and Known Flakes"]
    B --> C["Prepare Tools and Environment"]
    C --> D["Run Browser/API/Load Steps"]
    D --> E{"Failure Detected?"}
    E -->|No| F["Emit Pass Result"]
    E -->|Yes| G["Collect Evidence"]
    G --> H["Run Initial Triage"]
    H --> I["Write Failure Bundle"]
    I --> J["Return Structured Report"]
```

建议 graph state：

```json
{
  "workflow_run_id": "string",
  "scenario_id": "string",
  "environment": "string",
  "steps": [],
  "tool_events": [],
  "artifacts": [],
  "known_flakes": [],
  "triage_result": {},
  "status": "running"
}
```

节点职责：

- `Load Scenario Plan`
  加载预定义测试流程和断言
- `Load Memory and Known Flakes`
  加载历史波动、允许重试的外部故障模式
- `Prepare Tools and Environment`
  初始化浏览器、API token、日志查询上下文
- `Run Browser/API/Load Steps`
  执行具体验证步骤
- `Collect Evidence`
  截图、录屏、HAR、日志片段、trace
- `Run Initial Triage`
  判断更像真实缺陷、环境问题还是 flaky
- `Write Failure Bundle`
  归档结构化结果

## Coding Graph

coding agent 需要明确区分“只读诊断阶段”和“批准后修复阶段”。

```mermaid
flowchart TD
    A["Load Failure Bundle"] --> B["Map Failure to Code Surface"]
    B --> C["Read Repo and Search Context"]
    C --> D["Generate Diagnosis Report"]
    D --> E{"Fix Approved?"}
    E -->|No| F["Return Report Only"]
    E -->|Yes| G["Enable Fix Tools"]
    G --> H["Apply Patch"]
    H --> I["Run Targeted Regression"]
    I --> J["Generate PR Summary"]
    J --> K["Open Draft PR"]
```

建议 graph state：

```json
{
  "workflow_run_id": "string",
  "failure_bundle_uri": "string",
  "repo_ref": "string",
  "suspected_files": [],
  "diagnosis": {},
  "patch_plan": {},
  "regression_results": {},
  "fix_approved": false
}
```

节点职责：

- `Load Failure Bundle`
  读取 validator 的结构化证据
- `Map Failure to Code Surface`
  将错误现象映射到可能的模块和文件
- `Read Repo and Search Context`
  只读分析代码、日志、历史变更
- `Generate Diagnosis Report`
  产出根因分析、风险点和修复建议
- `Enable Fix Tools`
  在审批后切换到可编辑工具集
- `Apply Patch`
  只在 fix branch 操作
- `Run Targeted Regression`
  执行最小必要回归
- `Generate PR Summary`
  输出变更摘要、风险和验证结果

## Sandbox Images

### Validator Image

建议基础镜像内容：

- Ubuntu 22.04
- Python 3.12
- Node.js 20
- Playwright browsers
- k6 或 Locust
- curl、jq、ripgrep、git
- screenshot / image diff 工具
- OpenTelemetry exporter 或日志查询 CLI

### Coding Image

建议基础镜像内容：

- Ubuntu 22.04
- Python 3.12
- Node.js 20
- git、ripgrep、fd、jq
- 语言工具链和项目依赖缓存
- repo local mirror mount
- patch / diff / formatter / test runner

`coding image` 中默认不注入写权限 credential。只有进入 fix 阶段后，才下发限权 bot token 或短期凭据。

## Tooling Model

工具层面参考 Cursor 的理念，但要按角色和阶段拆分为多套 manifest，而不是“一套全能工具”。

### Design Principles

- 工具默认最小权限
- 工具清单由 control plane 下发
- 工具执行全量记录到 audit log
- 写工具与危险 shell 必须分离
- 尽量以结构化工具替代任意 shell

### Shared Utility Tools

这些工具可在两类 sandbox 中复用，但权限不同：

- `read_file`
- `list_dir`
- `grep_search`
- `glob_search`
- `fetch_artifact`
- `write_artifact`
- `run_structured_shell`
- `git_show_ref`
- `git_diff_refs`

### Validator Tool Set

建议 validator 使用以下工具：

- `browser_open`
- `browser_click`
- `browser_type`
- `browser_wait`
- `browser_extract`
- `browser_screenshot`
- `browser_console_logs`
- `browser_network_har`
- `http_request`
- `load_probe`
- `log_query`
- `trace_query`
- `metrics_query`
- `compare_screenshot`
- `memory_read`
- `artifact_write`

禁用工具：

- `edit_file`
- `apply_patch`
- `git_commit`
- `git_push`
- `open_pr`

### Coding Tool Set: Read-only Stage

建议 coding agent 只读阶段使用以下工具：

- `read_file`
- `list_dir`
- `grep_search`
- `glob_search`
- `git_show_ref`
- `git_diff_refs`
- `git_blame`
- `search_symbol`
- `run_tests_readonly`
- `run_linter_readonly`
- `read_failure_bundle`
- `log_query`

禁用工具：

- `edit_file`
- `apply_patch`
- `git_checkout_new_branch`
- `git_commit`
- `git_push`
- `open_pr`

### Coding Tool Set: Fix Stage

批准后切换到 fix 工具集：

- `edit_file`
- `apply_patch`
- `create_fix_branch`
- `run_tests_targeted`
- `run_formatter`
- `git_commit`
- `git_push_fix_branch`
- `open_draft_pr`
- `attach_artifacts_to_pr`

仍应禁用：

- `push_main`
- `merge_pr`
- `modify_secrets`
- `unrestricted_shell`

### Structured Shell Design

即使保留 shell，也建议采用受限结构化命令白名单，而不是给 agent 完整 bash。

例如：

- Allowed categories
  - `git status`
  - `git show`
  - `pytest path::test_name`
  - `npm test -- path`
  - `npm run build`
  - `python -m ...` 的只读分析命令
- Forbidden categories
  - `curl` 任意外网上传
  - `sudo`
  - `rm -rf`
  - 修改系统配置
  - 任意网络扫描

## Tool Manifest Example

```json
{
  "tool_profile": "coding-readonly",
  "tools": [
    {"name": "read_file", "mode": "read"},
    {"name": "grep_search", "mode": "read"},
    {"name": "git_show_ref", "mode": "read"},
    {"name": "run_tests_readonly", "mode": "exec", "scope": "whitelist"},
    {"name": "log_query", "mode": "read"}
  ],
  "restrictions": {
    "network": "internal-only",
    "git_push": false,
    "filesystem_write": false
  }
}
```

## GitHub Actions Pipeline Design

建议至少拆成三类 workflow：

### 1. Preprod Validation Workflow

触发条件：

- pull request 更新后
- merge 到主分支后的预发部署完成
- 手动触发

主步骤：

1. checkout repo
2. build metadata
3. call harness control plane `start_workflow(trigger=preprod_ci)`
4. 等待 validator 结果
5. 将 run URL 写入 GitHub check
6. 如失败则等待人工确认 gate
7. 如批准则继续 coding graph
8. draft PR 创建后回写链接

### 2. Scheduled Probe Workflow

触发条件：

- `schedule` 每小时运行

主步骤：

1. call harness control plane `start_workflow(trigger=scheduled_probe)`
2. validator 跑外部稳定性探测
3. 产出报告
4. 如有异常则创建 GitHub issue 或发送通知
5. 如命中 runbook 类修复且被批准，则进入修复流程

### 3. Developer Self-heal Workflow

触发条件：

- `workflow_dispatch`
- 开发者在 PR comment 中输入触发命令，例如 `/self-heal`

主步骤：

1. 针对当前 feature branch 启动 validator
2. 高置信失败自动进入 coding read-only diagnosis
3. 命中 auto-fix policy 后自动修复到派生分支
4. 创建面向开发者分支的 PR

## GitHub Actions Example Shape

```mermaid
flowchart TD
    A["GitHub Event"] --> B["Action Job: Start Harness Run"]
    B --> C["POST /workflow-runs"]
    C --> D["Control Plane Creates Sandboxes"]
    D --> E["Validator Graph Executes"]
    E --> F{"Failure?"}
    F -->|No| G["Mark Check Passed"]
    F -->|Yes| H["Publish Failure Bundle Link"]
    H --> I{"Human confirms bug?"}
    I -->|No| J["Close run as noise"]
    I -->|Yes| K["Coding Graph Diagnosis"]
    K --> L{"Human approves fix?"}
    L -->|No| M["Create issue / report only"]
    L -->|Yes| N["Enable fix branch write"]
    N --> O["Patch + Regression + Draft PR"]
    O --> P["Human reviews PR"]
```

## GitHub Integration Strategy

建议通过 GitHub App 或专用 bot identity 做以下动作：

- 创建 check run
- 在 PR 中回写 run 状态
- 创建或更新 draft PR
- 上传 artifact link
- 管理 label，例如 `agent-diagnosed`、`awaiting-bug-review`、`awaiting-fix-approval`

建议审批入口尽量落在 GitHub 内部，减少上下文切换。

## Branch Strategy

建议分支命名：

- 预发修复分支：
  `agent/fix/{workflow_run_id}`
- 开发者自愈分支：
  `agent/self-heal/{base_branch}/{workflow_run_id}`

建议 PR 策略：

- validator 失败后，不自动直接新开 PR
- coding diagnosis 完成且 fix 获批后，才允许创建 Draft PR
- 只有 GitHub branch protection 全绿且人类 review 通过，才允许 merge

## Data Model

建议数据库核心表：

- `workflow_runs`
  - id
  - trigger_type
  - status
  - repo
  - git_sha
  - scenario_set
  - created_at
- `sandbox_sessions`
  - id
  - workflow_run_id
  - role
  - profile
  - status
  - permissions
- `artifacts`
  - id
  - workflow_run_id
  - scenario_id
  - type
  - uri
  - metadata
- `approvals`
  - id
  - workflow_run_id
  - gate_type
  - approver
  - decision
  - decided_at
- `patches`
  - id
  - workflow_run_id
  - branch_name
  - commit_sha
  - pr_number

## Security Boundaries

### Validator Sandbox

- 允许访问预发和观测面
- 不允许访问 git write credential
- 不允许访问主仓库写入 token

### Coding Sandbox

- 默认不允许访问预发业务环境
- 只允许读取 artifact 和 repo
- fix 阶段只拿到短期 fix-branch push token
- 禁止使用主分支写权限

### Approval Security

- 审批操作要落到有身份的 GitHub 用户
- 所有批准事件都需要写审计表
- bot 不能自己批准自己的 PR

## Rollout Recommendation

### Step 1: Control Plane MVP

- FastAPI + PostgreSQL + MinIO
- OpenSandbox manager
- workflow run API
- validator graph 原型

### Step 2: Validator-first Delivery

- Playwright + API + artifact bundle
- GitHub Actions 集成
- 人工确认 bug gate

### Step 3: Read-only Coding Diagnosis

- coding graph 只读模式
- diagnosis report 输出
- GitHub comment / check integration

### Step 4: Approved Fix Mode

- fix branch token
- patch apply
- targeted regression
- draft PR

### Step 5: Developer Self-heal

- feature branch workflow_dispatch
- auto-fix policy
- developer review loop

## Recommended Repository Layout

如果后续要在当前仓库内落地，可以考虑新增：

```text
automation/
  control_plane/
    app/
      api/
      services/
      models/
      policies/
      adapters/
  graphs/
    validator/
    coding/
  sandbox_profiles/
    validator-linux-browser/
    coding-linux-readonly/
    coding-linux-fix/
  prompts/
    validator/
    coding/
  schemas/
    failure_bundle.schema.json
    diagnosis_report.schema.json
  .github/
    workflows/
      harness-preprod.yml
      harness-scheduled-probe.yml
      harness-self-heal.yml
```

## Recommendation

技术选型上，这套组合是合理的：

- `OpenSandbox` 负责安全隔离和权限边界
- `LangGraph` 负责 agent 工作流和状态驱动
- `GitHub Actions` 负责事件触发和 CI 接入
- `Playwright + API probe + load probe` 负责验证面
- `GitHub App + branch protection` 负责最终治理面

最关键的不是先把 agent 做得多聪明，而是先把这三层打牢：

- control plane 的状态和审批
- sandbox 的权限和隔离
- artifact 和工具协议的标准化

只有这三层稳了，后续自动 triage、自动修复和开发分支自愈能力才会真正可持续。
