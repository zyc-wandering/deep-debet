import { TraceEntry } from "../types";

interface Props {
  traceEntries: TraceEntry[];
  traceJournalPath: string;
}

function formatClock(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "--:--:--";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function TracePanel({ traceEntries, traceJournalPath }: Props) {
  const recent = [...traceEntries].reverse().slice(0, 12);
  const traceId = traceEntries[0]?.trace.trace_id || "";

  return (
    <section className="sidebar-panel trace-panel">
      <div className="sidebar-panel-head">
        <h4>Trace</h4>
        <span>{traceEntries.length}</span>
      </div>

      <div className="trace-meta-grid">
        <article className="sidebar-stat-card">
          <span>Trace ID</span>
          <strong className="trace-code">{traceId ? traceId.slice(0, 8) : "--"}</strong>
        </article>
        <article className="sidebar-stat-card">
          <span>Journal</span>
          <strong className="trace-code">{traceJournalPath ? "ready" : "--"}</strong>
        </article>
      </div>

      {traceJournalPath && <p className="trace-path">{traceJournalPath}</p>}

      <div className="trace-list">
        {recent.length === 0 ? (
          <p className="sidebar-empty">Trace events will appear here once the stream starts.</p>
        ) : (
          recent.map((entry) => (
            <article key={entry.id} className="trace-item">
              <div className="trace-item-head">
                <strong>#{entry.trace.event_seq}</strong>
                <time>{formatClock(entry.trace.emitted_at)}</time>
              </div>
              <p className="trace-summary">{entry.summary}</p>
              <div className="trace-item-meta">
                <span>{entry.event}</span>
                {entry.trace.span_name && <span>{entry.trace.span_name}</span>}
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
