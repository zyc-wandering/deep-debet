import { useEffect, useMemo, useState } from "react";
import { DebateLine } from "../types";
import { useDebateStore } from "../store/debateStore";
import { DebateStream } from "../components/DebateStream";
import { Timer } from "../components/Timer";

interface Props {
  onStop: () => void;
}

export function DebateRoomPage({ onStop }: Props) {
  const currentTab = useDebateStore((s) => s.currentTab);
  const setTab = useDebateStore((s) => s.setTab);

  const status = useDebateStore((s) => s.status);
  const phase = useDebateStore((s) => s.phase);
  const phaseLabel = useDebateStore((s) => s.phaseLabel);
  const debateDeadlineMs = useDebateStore((s) => s.debateDeadlineMs);
  const debaters = useDebateStore((s) => s.debaters);
  const lines = useDebateStore((s) => s.lines);
  const buffers = useDebateStore((s) => s.liveBuffers);
  const hostResearch = useDebateStore((s) => s.hostResearch);
  const hostSummary = useDebateStore((s) => s.hostSummary);
  const images = useDebateStore((s) => s.images);
  const reportMarkdown = useDebateStore((s) => s.reportMarkdown);
  const activities = useDebateStore((s) => s.activities);

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
    const live = Object.entries(buffers).map(([key, content]) => {
      const lastDash = key.lastIndexOf("-");
      const speaker = lastDash > 0 ? key.slice(0, lastDash) : key;
      const turnId = Number(lastDash > 0 ? key.slice(lastDash + 1) : 0);
      return { key, speaker, turnId, content, isLive: true };
    });
    return [...lines, ...live].sort((a, b) => a.turnId - b.turnId);
  }, [lines, buffers]);

  const running = status === "running";

  // Auto-switch tabs based on phase
  useEffect(() => {
    const inDebateStage = phase === "opening" || phase === "free_debate" || phase === "closing";
    if (inDebateStage && currentTab === "host") {
      setTab("debate");
    } else if (phase === "complete" && currentTab !== "summary") {
      setTab("summary");
    }
  }, [phase, currentTab, setTab]);

  return (
    <div className="debate-room">
      {/* Header Navigation */}
      <header className="room-header">
        <div className="room-brand">
          <span className="room-logo">🎭</span>
          <span className="room-title">DebateAI Room</span>
        </div>

        <nav className="room-tabs">
          <button
            className={currentTab === "host" ? "active" : ""}
            onClick={() => setTab("host")}
            disabled={phase === "idle"}
          >
            主持人工作台
          </button>
          <button
            className={currentTab === "debate" ? "active" : ""}
            onClick={() => setTab("debate")}
            disabled={phase === "idle" || phase === "booting" || phase === "researching"}
          >
            辩论舞台
          </button>
          <button
            className={currentTab === "summary" ? "active" : ""}
            onClick={() => setTab("summary")}
            disabled={phase === "idle" || phase === "booting" || phase === "researching"}
          >
            总结报告
          </button>
        </nav>

        <div className="room-actions">
          {running && (
            <button className="stop-button" onClick={onStop}>
              结束辩论
            </button>
          )}
        </div>
      </header>

      {/* Main Content - Holy Grail Layout */}
      <div className="room-layout">
        {/* Left Sidebar */}
        <aside className="room-sidebar left">
          <div className="sidebar-section">
            <h4>辩手阵容</h4>
            <div className="sidebar-debaters">
              {debaters.length === 0 ? (
                <p className="sidebar-empty">等待生成...</p>
              ) : (
                debaters.map((d) => (
                  <div key={d.id} className="sidebar-debater">
                    {d.avatar_url ? (
                      <img src={d.avatar_url} alt={d.name} className="debater-thumb" />
                    ) : (
                      <div className="debater-thumb-placeholder">{d.avatar_emoji}</div>
                    )}
                    <div className="debater-info">
                      <span className="debater-name">{d.name}</span>
                      <span className="debater-stance">{d.stance.slice(0, 20)}...</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="sidebar-section">
            <h4>活动日志</h4>
            <div className="sidebar-activities">
              {activities.slice(-5).map((a) => (
                <div key={a.id} className={`sidebar-activity ${a.tone}`}>
                  <span className="activity-title">{a.title}</span>
                  <span className="activity-time">
                    {new Date(a.at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* Center Main Content */}
        <main className="room-main">
          {/* Host Workspace Tab */}
          {currentTab === "host" && (
            <div className="tab-content host-tab">
              <div className="host-workspace">
                <section className="workspace-section research-section">
                  <header className="section-header">
                    <h2>📝 主持人调研</h2>
                    <span className="phase-badge">{phaseLabel}</span>
                  </header>
                  <div className="research-content">
                    {hostResearch ? (
                      <div className="research-text">{hostResearch}</div>
                    ) : (
                      <div className="research-loading">
                        <div className="loading-spinner" />
                        <p>主持人正在收集背景资料...</p>
                      </div>
                    )}
                  </div>
                </section>

                <section className="workspace-section debaters-section">
                  <header className="section-header">
                    <h2>🎭 辩手配置</h2>
                  </header>
                  <div className="debaters-grid">
                    {debaters.length === 0 ? (
                      <div className="debaters-loading">
                        <div className="loading-spinner" />
                        <p>正在生成辩手角色...</p>
                      </div>
                    ) : (
                      debaters.map((d) => (
                        <div key={d.id} className="debater-config-card">
                          <div className="debater-avatar-wrapper">
                            {d.avatar_url ? (
                              <img src={d.avatar_url} alt={d.name} className="debater-avatar-img" />
                            ) : images.avatars[d.name] ? (
                              <img src={images.avatars[d.name]} alt={d.name} className="debater-avatar-img" />
                            ) : (
                              <div className="debater-avatar-loading">
                                <div className="loading-spinner small" />
                              </div>
                            )}
                          </div>
                          <div className="debater-config-info">
                            <h4>{d.name}</h4>
                            <p className="debater-config-bg">{d.background}</p>
                            <p className="debater-config-stance">{d.stance}</p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>

                {images.background && (
                  <section className="workspace-section scene-section">
                    <header className="section-header">
                      <h2>🎨 辩论场景</h2>
                    </header>
                    <div className="scene-image-wrapper">
                      <img src={images.background} alt="辩论场景" className="scene-image" />
                    </div>
                  </section>
                )}
              </div>
            </div>
          )}

          {/* Debate Stage Tab */}
          {currentTab === "debate" && (
            <div className="tab-content debate-tab">
              {images.background && (
                <div className="debate-stage-bg">
                  <img src={images.background} alt="辩论背景" className="stage-bg-image" />
                  <div className="stage-overlay" />
                </div>
              )}

              <div className="debate-stage-content">
                <header className="stage-header">
                  <Timer phase={phase} secondsLeft={secondsLeft} />
                  <div className="stage-status">
                    <span className={`status-dot ${running ? "live" : ""}`} />
                    <span>{phaseLabel}</span>
                  </div>
                </header>

                <DebateStream lines={mergedLines} />
              </div>
            </div>
          )}

          {/* Summary Tab */}
          {currentTab === "summary" && (
            <div className="tab-content summary-tab">
              <div className="summary-content">
                {images.summary && (
                  <div className="summary-poster">
                    <img src={images.summary} alt="辩论总结海报" />
                  </div>
                )}

                <div className="summary-report">
                  <header className="section-header">
                    <h2>📊 辩论报告</h2>
                  </header>
                  {reportMarkdown ? (
                    <div className="markdown-body" dangerouslySetInnerHTML={{ __html: formatMarkdown(reportMarkdown) }} />
                  ) : hostSummary ? (
                    <div className="summary-streaming">
                      <h3>主持人流式总结</h3>
                      <p>{hostSummary}</p>
                    </div>
                  ) : (
                    <div className="summary-loading">
                      <div className="loading-spinner" />
                      <p>正在生成总结报告...</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </main>

        {/* Right Sidebar */}
        <aside className="room-sidebar right">
          <div className="sidebar-section">
            <h4>辩论信息</h4>
            <div className="sidebar-info">
              <div className="info-item">
                <span className="info-label">当前阶段</span>
                <span className="info-value">{phaseLabel}</span>
              </div>
              <div className="info-item">
                <span className="info-label">发言轮次</span>
                <span className="info-value">{lines.length} 轮</span>
              </div>
              <div className="info-item">
                <span className="info-label">剩余时间</span>
                <span className="info-value">
                  {secondsLeft > 0 ? formatTime(secondsLeft) : "--"}
                </span>
              </div>
            </div>
          </div>

          <div className="sidebar-section">
            <h4>快捷操作</h4>
            <div className="sidebar-actions">
              <button
                className="sidebar-action"
                onClick={() => setTab("host")}
                disabled={currentTab === "host" || phase === "idle"}
              >
                查看主持人工作台
              </button>
              <button
                className="sidebar-action"
                onClick={() => setTab("debate")}
                disabled={currentTab === "debate" || phase === "idle" || phase === "booting" || phase === "researching"}
              >
                进入辩论舞台
              </button>
              <button
                className="sidebar-action"
                onClick={() => setTab("summary")}
                disabled={currentTab === "summary" || phase === "idle" || phase === "booting" || phase === "researching"}
              >
                查看总结报告
              </button>
              {(phase === "complete" || phase === "error") && (
                <button
                  className="sidebar-action primary"
                  onClick={() => window.location.reload()}
                >
                  开始新辩论
                </button>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function formatMarkdown(md: string): string {
  // Simple markdown to HTML conversion
  return md
    .replace(/^### (.*$)/gim, "<h3>$1</h3>")
    .replace(/^## (.*$)/gim, "<h2>$1</h2>")
    .replace(/^# (.*$)/gim, "<h1>$1</h1>")
    .replace(/\*\*(.*)\*\*/gim, "<strong>$1</strong>")
    .replace(/\*(.*)\*/gim, "<em>$1</em>")
    .replace(/\n/gim, "<br />");
}
