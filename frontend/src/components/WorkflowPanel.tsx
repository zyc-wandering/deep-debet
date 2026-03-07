import { DebatePhase, WorkflowActivity } from "../types";

interface Props {
  phase: DebatePhase;
  phaseLabel: string;
  phaseDetail: string;
  hostResearch: string;
  activities: WorkflowActivity[];
  activeSpeaker: string;
  activeTurnId: number | null;
}

const steps = [
  {
    key: "booting",
    index: "01",
    title: "接收命题",
    description: "创建会话，锁定本轮参数。",
  },
  {
    key: "researching",
    index: "02",
    title: "主持人调研",
    description: "梳理背景、争议焦点与证据脉络。",
  },
  {
    key: "assembling",
    index: "03",
    title: "配置辩手",
    description: "生成分工明确的角色、立场与风格。",
  },
  {
    key: "debating",
    index: "04",
    title: "实时交锋",
    description: "逐轮输出观点、反驳和追问。",
  },
  {
    key: "summarizing",
    index: "05",
    title: "总结归档",
    description: "主持人收束争议并生成最终报告。",
  },
] as const;

const phaseOrder: Record<DebatePhase, number> = {
  idle: -1,
  booting: 0,
  researching: 1,
  assembling: 2,
  debating: 3,
  summarizing: 4,
  complete: 5,
  error: 5,
};

function getResearchExcerpt(text: string) {
  const normalized = text.trim().replace(/\n{3,}/g, "\n\n");
  if (!normalized) {
    return "提交辩题后，这里会持续滚动显示主持人正在整理的背景信息与判断框架。";
  }
  return normalized.slice(-360);
}

export function WorkflowPanel({
  phase,
  phaseLabel,
  phaseDetail,
  hostResearch,
  activities,
  activeSpeaker,
  activeTurnId,
}: Props) {
  const excerpt = getResearchExcerpt(hostResearch);
  const currentOrder = phaseOrder[phase];
  const recentActivities = [...activities].reverse().slice(0, 5);

  return (
    <section className="panel workflow-panel">
      <div className="section-head">
        <div>
          <p className="eyebrow">Workflow</p>
          <h2>发起后的工作流可视化</h2>
        </div>
        <div className="phase-badge">
          <span className="phase-dot" />
          <strong>{phaseLabel}</strong>
        </div>
      </div>

      <p className="workflow-summary">{phaseDetail}</p>

      <div className="workflow-grid">
        <ol className="workflow-steps">
          {steps.map((step) => {
            const order = phaseOrder[step.key];
            const state =
              phase === "error"
                ? order <= currentOrder
                  ? "error"
                  : "pending"
                : currentOrder > order
                  ? "done"
                  : currentOrder === order
                    ? "active"
                    : "pending";
            return (
              <li key={step.key} className={`workflow-step ${state}`}>
                <span className="workflow-step-index">{step.index}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.description}</p>
                </div>
              </li>
            );
          })}
        </ol>

        <div className="workflow-inspector">
          <div className="inspector-card">
            <span className="inspector-label">当前焦点</span>
            {activeSpeaker ? (
              <p className="inspector-main">
                {activeSpeaker} 正在生成第 {activeTurnId !== null ? activeTurnId + 1 : "-"} 轮发言
              </p>
            ) : (
              <p className="inspector-main">{phaseLabel}</p>
            )}
            <p className="muted">{phaseDetail}</p>
          </div>

          <div className="inspector-card">
            <span className="inspector-label">主持人研究摘录</span>
            <article className="research-excerpt">{excerpt}</article>
          </div>
        </div>
      </div>

      <div className="activity-log">
        <div className="section-head compact">
          <h3>过程日志</h3>
          <span className="muted">最近 {recentActivities.length} 条</span>
        </div>
        {recentActivities.length === 0 ? (
          <p className="muted">系统启动后，会把每个关键阶段写入这里。</p>
        ) : (
          <div className="activity-list">
            {recentActivities.map((item) => (
              <article key={item.id} className={`activity-item ${item.tone}`}>
                <div className="activity-meta">
                  <strong>{item.title}</strong>
                  <time>{new Date(item.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
                </div>
                {item.detail && <p>{item.detail}</p>}
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
