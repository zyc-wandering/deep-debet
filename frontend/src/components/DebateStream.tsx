import { useEffect, useRef, useState } from "react";
import { DebateLine } from "../types";

interface Props {
  lines: DebateLine[];
}

function StreamingText({ content, isLive }: { content: string; isLive?: boolean }) {
  // Direct display - no animation delay, content is streamed from backend
  return (
    <span className="streaming-content">
      {content}
      {isLive && <span className="cursor" />}
    </span>
  );
}

export function DebateStream({ lines }: Props) {
  const scrollRef = autoScroll(lines);

  return (
    <section className="panel stream-panel">
      <div className="section-head">
        <div>
          <p className="eyebrow">Transcript</p>
          <h2>实时辩论记录</h2>
        </div>
        <span className="muted">{lines.length} 段发言</span>
      </div>

      <div ref={scrollRef} className="stream-list">
        {lines.length === 0 && <p className="muted empty-block">辩手就位后，第一轮发言会在这里实时展开。</p>}

        {lines.map((line) => (
          <article key={line.key} className={`bubble ${line.isLive ? "live" : ""}`}>
            <header>
              <div className="bubble-title">
                <strong>{line.speaker}</strong>
                {line.isLive && (
                  <span className="live-tag">
                    <span className="pulse" />
                    实时生成中
                  </span>
                )}
              </div>
              <span className="turn">第 {line.turnId + 1} 轮</span>
            </header>
            <p className="streaming-text">
              <StreamingText content={line.content} isLive={line.isLive} />
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function autoScroll(lines: DebateLine[]) {
  const ref = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  useEffect(() => {
    const el = ref.current;
    if (!el || !shouldAutoScroll) return;

    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    if (isNearBottom || lines.some(l => l.isLive)) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lines, shouldAutoScroll]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onScroll = () => {
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
      setShouldAutoScroll(isNearBottom);
    };

    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return ref;
}
