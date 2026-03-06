import { DebateLine } from "../types";

interface Props {
  lines: DebateLine[];
}

export function DebateStream({ lines }: Props) {
  return (
    <section className="panel stream-panel">
      <h2>实时辩论</h2>
      <div className="stream-list">
        {lines.length === 0 && <p className="muted">等待第一位辩手发言…</p>}
        {lines.map((line) => (
          <article key={line.key} className="bubble">
            <header>
              <strong>{line.speaker}</strong>
              <span className="turn">Round {line.turnId + 1}</span>
            </header>
            <p>{line.content}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

