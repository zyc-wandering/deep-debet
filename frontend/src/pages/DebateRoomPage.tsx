import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useDebate } from "../hooks/useDebate";
import { useDebateStore } from "../store/debateStore";
import { DebateStream } from "../components/DebateStream";
import { Timer } from "../components/Timer";

interface Props {
  onStop: () => void;
}

export function DebateRoomPage({ onStop }: Props) {
  const debate = useDebate();
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
  const sessionId = useDebateStore((s) => s.sessionId);
  const errorMessage = useDebateStore((s) => s.errorMessage);

  const focusOptions = useDebateStore((s) => s.focusOptions);
  const selectedFocusId = useDebateStore((s) => s.selectedFocusId);
  const intensityDraft = useDebateStore((s) => s.intensityDraft);
  const userContextDraft = useDebateStore((s) => s.userContextDraft);
  const isConfigurationReady = useDebateStore((s) => s.isConfigurationReady);
  const setSelectedFocus = useDebateStore((s) => s.setSelectedFocus);
  const setIntensityDraft = useDebateStore((s) => s.setIntensityDraft);
  const setUserContextDraft = useDebateStore((s) => s.setUserContextDraft);

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
  const canConfigure = phase === "configuring" && isConfigurationReady && Boolean(selectedFocusId);

  useEffect(() => {
    if (phase === "complete" && currentTab !== "summary") {
      setTab("summary");
    }
  }, [phase, currentTab, setTab]);

  const handleConfigure = async () => {
    if (!sessionId || !selectedFocusId) return;
    await debate.configure({
      session_id: sessionId,
      pre_debate_config: {
        selected_focus_id: selectedFocusId,
        intensity: intensityDraft,
        user_context: userContextDraft,
      },
    });
  };

  return (
    <div className="debate-room">
      <header className="room-header">
        <div className="room-brand">
          <span className="room-logo">DR</span>
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
            disabled={!debaters.length}
          >
            辩论舞台
          </button>
          <button
            className={currentTab === "summary" ? "active" : ""}
            onClick={() => setTab("summary")}
            disabled={phase !== "complete"}
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

      <div className="room-layout">
        <aside className="room-sidebar left">
          <div className="sidebar-section">
            <h4>辩手阵容</h4>
            <div className="sidebar-debaters">
              {debaters.length === 0 ? (
                <p className="sidebar-empty">等待生成...</p>
              ) : (
                debaters.map((debater) => (
                  <div key={debater.id} className="sidebar-debater">
                    {debater.avatar_url ? (
                      <img src={debater.avatar_url} alt={debater.name} className="debater-thumb" />
                    ) : (
                      <div className="debater-thumb-placeholder">{debater.avatar_emoji}</div>
                    )}
                    <div className="debater-info">
                      <span className="debater-name">{debater.name}</span>
                      <span className="debater-stance">{debater.stance.slice(0, 24)}...</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="sidebar-section">
            <h4>活动日志</h4>
            <div className="sidebar-activities">
              {activities.slice(-5).map((activity) => (
                <div key={activity.id} className={`sidebar-activity ${activity.tone}`}>
                  <span className="activity-title">{activity.title}</span>
                  <span className="activity-time">
                    {new Date(activity.at).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </aside>

        <main className="room-main">
          {errorMessage && <p className="error room-error">{errorMessage}</p>}

          {currentTab === "host" && (
            <div className="tab-content host-tab">
              <div className="host-workspace">
                <section className="workspace-section research-section">
                  <header className="section-header">
                    <h2>主持人调研</h2>
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

                {phase === "configuring" && (
                  <section className="workspace-section configuration-section">
                    <header className="section-header">
                      <h2>选择你更关心的讨论切面</h2>
                    </header>
                    <div className="configuration-panel">
                      <p className="form-intro">
                        主持人已经基于议题研究整理出几个更值得展开的切面。这里选择的是你更关心的讨论维度，不是你想要的答案。
                      </p>

                      <div className="focus-options-grid">
                        {focusOptions.map((option) => (
                          <button
                            key={option.id}
                            type="button"
                            className={`focus-option-card ${selectedFocusId === option.id ? "selected" : ""}`}
                            onClick={() => setSelectedFocus(option.id)}
                          >
                            <strong>{option.name}</strong>
                            <span>{option.description}</span>
                          </button>
                        ))}
                      </div>

                      <div className="grid config-grid">
                        <label className="field">
                          <span className="field-label">交锋强度</span>
                          <select
                            value={intensityDraft}
                            onChange={(e) =>
                              setIntensityDraft(e.target.value as "mild" | "balanced" | "intense")
                            }
                          >
                            <option value="mild">Mild</option>
                            <option value="balanced">Balanced</option>
                            <option value="intense">Intense</option>
                          </select>
                        </label>
                      </div>

                      <label className="field">
                        <span className="field-label">补充背景（可选）</span>
                        <textarea
                          className="topic-textarea"
                          rows={4}
                          value={userContextDraft}
                          onChange={(e) => setUserContextDraft(e.target.value)}
                          placeholder="补充场景约束、现实背景或你掌握的上下文。系统会把这些当作议题背景，而不是你的立场。"
                        />
                      </label>

                      <div className="actions">
                        <button
                          type="button"
                          className="primary-button"
                          disabled={!canConfigure}
                          onClick={() => void handleConfigure()}
                        >
                          继续辩论
                        </button>
                      </div>
                    </div>
                  </section>
                )}

                <section className="workspace-section debaters-section">
                  <header className="section-header">
                    <h2>辩手配置</h2>
                  </header>
                  <div className="debaters-grid">
                    {debaters.length === 0 ? (
                      <div className="debaters-loading">
                        <div className="loading-spinner" />
                        <p>配置完成后将生成辩手角色...</p>
                      </div>
                    ) : (
                      debaters.map((debater) => (
                        <div key={debater.id} className="debater-config-card">
                          <div className="debater-avatar-wrapper">
                            {debater.avatar_url ? (
                              <img src={debater.avatar_url} alt={debater.name} className="debater-avatar-img" />
                            ) : images.avatars[debater.name] ? (
                              <img src={images.avatars[debater.name]} alt={debater.name} className="debater-avatar-img" />
                            ) : (
                              <div className="debater-avatar-loading">
                                <div className="loading-spinner small" />
                              </div>
                            )}
                          </div>
                          <div className="debater-config-info">
                            <h4>{debater.name}</h4>
                            <p className="debater-config-bg">{debater.background}</p>
                            <p className="debater-config-stance">{debater.stance}</p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>

                {images.background && (
                  <section className="workspace-section scene-section">
                    <header className="section-header">
                      <h2>辩论场景</h2>
                    </header>
                    <div className="scene-image-wrapper">
                      <img src={images.background} alt="辩论场景" className="scene-image" />
                    </div>
                  </section>
                )}
              </div>
            </div>
          )}

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
                    <h2>辩论报告</h2>
                  </header>
                  {reportMarkdown ? (
                    <article className="markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{reportMarkdown}</ReactMarkdown>
                    </article>
                  ) : hostSummary ? (
                    <div className="summary-streaming markdown-body">
                      <h3>主持人流式总结</h3>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{hostSummary}</ReactMarkdown>
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
                <span className="info-value">{secondsLeft > 0 ? formatTime(secondsLeft) : "--"}</span>
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
                disabled={currentTab === "debate" || !debaters.length}
              >
                进入辩论舞台
              </button>
              <button
                className="sidebar-action"
                onClick={() => setTab("summary")}
                disabled={currentTab === "summary" || phase !== "complete"}
              >
                查看总结报告
              </button>
              {(phase === "complete" || phase === "error") && (
                <button className="sidebar-action primary" onClick={() => window.location.reload()}>
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
