import { useEffect, useMemo, useState } from "react";
import { DebaterCard } from "../components/DebaterCard";
import { DebateStream } from "../components/DebateStream";
import { ReportView } from "../components/ReportView";
import { Timer } from "../components/Timer";
import { TopicInput } from "../components/TopicInput";
import { useDebate } from "../hooks/useDebate";
import { useDebateStore } from "../store/debateStore";
import { DebateStartRequest } from "../types";

export function DebatePage() {
  const debate = useDebate();
  const status = useDebateStore((s) => s.status);
  const debateDeadlineMs = useDebateStore((s) => s.debateDeadlineMs);
  const debaters = useDebateStore((s) => s.debaters);
  const lines = useDebateStore((s) => s.lines);
  const buffers = useDebateStore((s) => s.liveBuffers);
  const hostResearch = useDebateStore((s) => s.hostResearch);
  const hostSummary = useDebateStore((s) => s.hostSummary);
  const reportPath = useDebateStore((s) => s.reportPath);
  const reportMarkdown = useDebateStore((s) => s.reportMarkdown);
  const errorMessage = useDebateStore((s) => s.errorMessage);

  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    if (!debateDeadlineMs || status !== "running") return;
    const tick = () => {
      const left = Math.max(0, Math.floor((debateDeadlineMs - Date.now()) / 1000));
      setSecondsLeft(left);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [debateDeadlineMs, status]);

  const mergedLines = useMemo(() => {
    const live = Object.entries(buffers).map(([key, content]) => {
      const lastDash = key.lastIndexOf("-");
      const speaker = lastDash > 0 ? key.slice(0, lastDash) : key;
      const turnId = Number(lastDash > 0 ? key.slice(lastDash + 1) : 0);
      return { key, speaker, turnId, content };
    });
    return [...lines, ...live].sort((a, b) => a.turnId - b.turnId);
  }, [lines, buffers]);

  const running = status === "running";

  const handleStart = async (payload: DebateStartRequest) => {
    setSecondsLeft(0);
    await debate.start(payload);
  };

  const handleStop = async () => {
    await debate.stop();
  };

  const finalMarkdown =
    reportMarkdown || (hostSummary ? `## 主持人流式总结\n\n${hostSummary}` : "");

  return (
    <main className="page">
      <header className="hero">
        <div>
          <h1>DebateAI Room</h1>
          <p>让多个 AI 角色从对立角度拆解同一问题，给你更完整的思考框架。</p>
        </div>
        <Timer running={running} secondsLeft={secondsLeft} />
      </header>

      <section className="panel">
        <TopicInput running={running} onStart={handleStart} onStop={handleStop} />
        {errorMessage && <p className="error">{errorMessage}</p>}
      </section>

      <section className="panel">
        <h2>主持人调研简报</h2>
        <article className="brief">{hostResearch || "开始后这里会出现主持人调研摘要。"}</article>
      </section>

      <section className="debater-grid">
        {debaters.map((debater) => (
          <DebaterCard key={debater.id} debater={debater} />
        ))}
      </section>

      <DebateStream lines={mergedLines} />
      <ReportView reportPath={reportPath} markdown={finalMarkdown} />
    </main>
  );
}
