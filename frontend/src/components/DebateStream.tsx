import { DebateLine } from "../types";

interface Props {
  lines: DebateLine[];
}

export function DebateStream({ lines }: Props) {
  return (
    <section className="panel stream-panel">
      <div className="section-head">
        <div>
          <p className="eyebrow">Transcript</p>
          <h2>实时辩论记录</h2>
        </div>
        <span className="muted">{lines.length} 段发言</span>
      </div>

      <div className="stream-list">
        {lines.length === 0 && <p className="muted empty-block">辩手就位后，第一轮发言会在这里实时展开。</p>}

        {lines.map((line) => (
          <article key={line.key} className={`bubble ${line.isLive ? "live" : ""}`}>
            <header>
              <div className="bubble-title">
                <strong>{line.speaker}</strong>
                {line.isLive && <span className="live-tag">实时生成</span>}
              </div>
              <span className="turn">第 {line.turnId + 1} 轮</span>
            </header>
            <p>{line.content}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
