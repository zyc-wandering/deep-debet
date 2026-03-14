import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DebateLine, DebateStage, PreparingTurn } from "../types";
import { extractDebateSpeechContent } from "../utils/debateSpeech";

interface Props {
  lines: DebateLine[];
  preparingTurn?: PreparingTurn | null;
}

const stageLabels: Record<DebateStage, string> = {
  opening: "Opening",
  free_debate: "Free Debate",
  closing: "Closing",
  summary: "Summary",
};

function StreamingMarkdown({ content, stage, isLive }: { content: string; stage?: DebateStage; isLive?: boolean }) {
  const markdown = extractDebateSpeechContent(content, stage);

  return (
    <div className="streaming-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      {isLive && <span className="cursor streaming-cursor" />}
    </div>
  );
}

function PreparingBubble({ turn }: { turn: PreparingTurn }) {
  return (
    <article className="bubble preparing">
      <header>
        <div className="bubble-title">
          <strong>{turn.speaker}</strong>
          {turn.stage && <span className="stage-tag">{stageLabels[turn.stage]}</span>}
          <span className="live-tag preparing-tag">
            <span className="pulse loading-pulse" />
            <span className="loading-word">loading</span>
          </span>
        </div>
        <span className="turn">Turn {turn.turnId + 1}</span>
      </header>

      <div className="preparing-copy">
        <p className="streaming-text">{turn.speaker} is preparing the next answer...</p>
        <span className="preparing-subline">The system is assembling context and generating the next response.</span>
      </div>
    </article>
  );
}

export function DebateStream({ lines, preparingTurn }: Props) {
  const scrollRef = autoScroll(lines, Boolean(preparingTurn));

  return (
    <section className="panel stream-panel">
      <div className="section-head compact">
        <div>
          <h2>Debate Transcript</h2>
        </div>
        <span className="badge">{lines.length} turns</span>
      </div>

      <div ref={scrollRef} className="stream-list">
        {lines.length === 0 && !preparingTurn && (
          <p className="muted empty-block">
            Once the debaters start speaking, the live transcript will appear here.
          </p>
        )}

        {lines.map((line) => (
          <article key={line.key} className={`bubble ${line.isLive ? "live" : ""}`}>
            <header>
              <div className="bubble-title">
                <strong>{line.speaker}</strong>
                {line.stage && <span className="stage-tag">{stageLabels[line.stage]}</span>}
                {line.isLive && (
                  <span className="live-tag">
                    <span className="pulse" />
                    Streaming
                  </span>
                )}
              </div>
              <span className="turn">Turn {line.turnId + 1}</span>
            </header>

            <div className="streaming-text debate-line-markdown">
              <StreamingMarkdown content={line.content} stage={line.stage} isLive={line.isLive} />
            </div>
          </article>
        ))}

        {preparingTurn && <PreparingBubble turn={preparingTurn} />}
      </div>
    </section>
  );
}

function autoScroll(lines: DebateLine[], hasPreparingTurn: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  useEffect(() => {
    const el = ref.current;
    if (!el || !shouldAutoScroll) return;

    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    if (isNearBottom || hasPreparingTurn || lines.some((line) => line.isLive)) {
      el.scrollTop = el.scrollHeight;
    }
  }, [hasPreparingTurn, lines, shouldAutoScroll]);

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
