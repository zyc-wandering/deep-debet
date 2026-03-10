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
  { key: "booting", index: "01", title: "Boot", description: "Create the session and prepare the host workspace." },
  { key: "researching", index: "02", title: "Research", description: "Collect background, evidence, and open questions." },
  { key: "assembling", index: "03", title: "Assemble", description: "Generate debaters, roles, and stage setup." },
  { key: "opening", index: "04", title: "Opening", description: "Each debater states a starting position and judging frame." },
  { key: "free_debate", index: "05", title: "Free Debate", description: "Debaters challenge each other and deepen the disagreement." },
  { key: "closing", index: "06", title: "Closing", description: "Each debater gives a final position after the exchange." },
  { key: "summarizing", index: "07", title: "Summary", description: "The host synthesizes disagreements, consensus, and conditions." },
] as const;

const phaseOrder: Record<DebatePhase, number> = {
  idle: -1,
  booting: 0,
  researching: 1,
  assembling: 2,
  generating_background: 2.5,
  configuring: 2,
  opening: 3,
  free_debate: 4,
  closing: 5,
  summarizing: 6,
  generating_summary_image: 6.5,
  complete: 7,
  follow_up: 7,
  error: 7,
};

function getResearchExcerpt(text: string) {
  const normalized = text.trim().replace(/\n{3,}/g, "\n\n");
  if (!normalized) {
    return "Host research will appear here once the debate starts.";
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
          <h2>Debate execution flow</h2>
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
            <span className="inspector-label">Current focus</span>
            {activeSpeaker ? (
              <p className="inspector-main">
                {activeSpeaker} is generating turn {activeTurnId !== null ? activeTurnId + 1 : "-"}.
              </p>
            ) : (
              <p className="inspector-main">{phaseLabel}</p>
            )}
            <p className="muted">{phaseDetail}</p>
          </div>

          <div className="inspector-card">
            <span className="inspector-label">Host research excerpt</span>
            <article className="research-excerpt">{excerpt}</article>
          </div>
        </div>
      </div>

      <div className="activity-log">
        <div className="section-head compact">
          <h3>Recent activity</h3>
          <span className="muted">Last {recentActivities.length}</span>
        </div>
        {recentActivities.length === 0 ? (
          <p className="muted">Activity events will appear here after the run starts.</p>
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
