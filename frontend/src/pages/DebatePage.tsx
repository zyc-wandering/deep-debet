import { useEffect, useMemo, useState } from "react";
import { DebaterCard } from "../components/DebaterCard";
import { DebateStream } from "../components/DebateStream";
import { ReportView } from "../components/ReportView";
import { Timer } from "../components/Timer";
import { TopicInput } from "../components/TopicInput";
import { WorkflowPanel } from "../components/WorkflowPanel";
import { useDebate } from "../hooks/useDebate";
import { useDebateStore } from "../store/debateStore";
import { DebateStartRequest } from "../types";

export function DebatePage() {
  const debate = useDebate();
  const status = useDebateStore((s) => s.status);
  const phase = useDebateStore((s) => s.phase);
  const phaseLabel = useDebateStore((s) => s.phaseLabel);
  const phaseDetail = useDebateStore((s) => s.phaseDetail);
  const debateDeadlineMs = useDebateStore((s) => s.debateDeadlineMs);
  const debaters = useDebateStore((s) => s.debaters);
  const lines = useDebateStore((s) => s.lines);
  const buffers = useDebateStore((s) => s.liveBuffers);
  const hostResearch = useDebateStore((s) => s.hostResearch);
  const hostSummary = useDebateStore((s) => s.hostSummary);
  const reportPath = useDebateStore((s) => s.reportPath);
  const reportMarkdown = useDebateStore((s) => s.reportMarkdown);
  const errorMessage = useDebateStore((s) => s.errorMessage);
  const activities = useDebateStore((s) => s.activities);
  const activeSpeaker = useDebateStore((s) => s.activeSpeaker);
  const activeTurnId = useDebateStore((s) => s.activeTurnId);

  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    const showTimer = phase === "opening" || phase === "free_debate" || phase === "closing";
    if (!debateDeadlineMs || !showTimer) {
      setSecondsLeft(0);
      return;
    }
    const tick = () => {
      const left = Math.max(0, Math.floor((debateDeadlineMs - Date.now()) / 1000));
      setSecondsLeft(left);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [debateDeadlineMs, phase]);

  const mergedLines = useMemo(() => {
    const live = Object.entries(buffers).map(([key, buffer]) => {
      const lastDash = key.lastIndexOf("-");
      const speaker = lastDash > 0 ? key.slice(0, lastDash) : key;
      const turnId = Number(lastDash > 0 ? key.slice(lastDash + 1) : 0);
      return { key, speaker, turnId, content: buffer.content, stage: buffer.stage, isLive: true };
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

  const finalMarkdown = reportMarkdown || (hostSummary ? `## 主持人流式总结\n\n${hostSummary}` : "");

  return (
    <main className="page">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">DebateAI Room</p>
          <h1>更克制，也更像一套真正可工作的辩论控制台。</h1>
          <p className="hero-intro">
            去掉夸张圆角、泛滥渐变和紫色模板感之后，辩题输入、准备流程、实时交锋与总结报告被组织到同一条清晰工作流中。
          </p>
        </div>

        <div className="hero-side">
          <Timer phase={phase} secondsLeft={secondsLeft} />
          <div className="hero-stats">
            <article>
              <span>当前阶段</span>
              <strong>{phaseLabel}</strong>
            </article>
            <article>
              <span>辩手数量</span>
              <strong>{debaters.length > 0 ? `${debaters.length} 位` : "--"}</strong>
            </article>
            <article>
              <span>过程日志</span>
              <strong>{activities.length} 条</strong>
            </article>
          </div>
        </div>
      </header>

      <section className="top-grid">
        <section className="panel composer-panel">
          <TopicInput running={running} onStart={handleStart} onStop={handleStop} />
          {errorMessage && <p className="error">{errorMessage}</p>}
        </section>

        <WorkflowPanel
          phase={phase}
          phaseLabel={phaseLabel}
          phaseDetail={phaseDetail}
          hostResearch={hostResearch}
          activities={activities}
          activeSpeaker={activeSpeaker}
          activeTurnId={activeTurnId}
        />
      </section>

      <section className="secondary-grid">
        <section className="panel research-panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Research</p>
              <h2>主持人研究工作台</h2>
            </div>
            <span className="muted">{hostResearch ? "实时更新中" : "等待启动"}</span>
          </div>
          <article className="brief research-body">
            {hostResearch || "提交辩题后，这里会流式显示主持人整理的背景信息、关键争议和判断框架。"}
          </article>
        </section>

        <section className="panel roster-panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Participants</p>
              <h2>辩手阵列</h2>
            </div>
            <span className="muted">{debaters.length > 0 ? `${debaters.length} 位已就位` : "待生成"}</span>
          </div>

          {debaters.length === 0 ? (
            <p className="muted empty-block">
              主持人完成调研后，会在这里生成角色定位清晰、分析框架不同的辩手配置。
            </p>
          ) : (
            <div className="debater-grid">
              {debaters.map((debater) => (
                <DebaterCard key={debater.id} debater={debater} />
              ))}
            </div>
          )}
        </section>
      </section>

      <DebateStream lines={mergedLines} />
      <ReportView reportPath={reportPath} markdown={finalMarkdown} />
    </main>
  );
}
