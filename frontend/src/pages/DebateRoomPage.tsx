import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DebateStream } from "../components/DebateStream";
import { Timer } from "../components/Timer";
import { useDebate } from "../hooks/useDebate";
import { useDebateStore } from "../store/debateStore";
import { DebatePhase } from "../types";

interface Props {
  onStop: () => void;
}

const roomSteps: Array<{ key: DebatePhase; label: string }> = [
  { key: "booting", label: "会话初始化" },
  { key: "researching", label: "主持人调研" },
  { key: "configuring", label: "选择讨论切面" },
  { key: "assembling", label: "生成辩手阵列" },
  { key: "opening", label: "开场陈述" },
  { key: "free_debate", label: "自由辩论" },
  { key: "closing", label: "总结陈词" },
  { key: "summarizing", label: "主持人总结" },
  { key: "generating_summary_image", label: "生成总结海报" },
  { key: "complete", label: "报告完成" },
];

const phaseOrder: Record<DebatePhase, number> = {
  idle: -1,
  booting: 0,
  researching: 1,
  assembling: 3,
  generating_background: 3,
  configuring: 2,
  opening: 4,
  free_debate: 5,
  closing: 6,
  summarizing: 7,
  generating_summary_image: 8,
  complete: 9,
  follow_up: 9,
  error: 9,
};

function clampTooltip(x: number, y: number) {
  const width = typeof window === "undefined" ? 320 : window.innerWidth;
  const height = typeof window === "undefined" ? 240 : window.innerHeight;
  const tooltipWidth = 320;
  const tooltipHeight = 260;

  return {
    x: Math.min(x + 20, width - tooltipWidth - 16),
    y: Math.min(Math.max(16, y - 48), height - tooltipHeight - 16),
  };
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function DebateRoomPage({ onStop }: Props) {
  const debate = useDebate();
  const currentTab = useDebateStore((s) => s.currentTab);
  const setTab = useDebateStore((s) => s.setTab);

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
  const images = useDebateStore((s) => s.images);
  const reportMarkdown = useDebateStore((s) => s.reportMarkdown);
  const activities = useDebateStore((s) => s.activities);
  const sessionId = useDebateStore((s) => s.sessionId);
  const errorMessage = useDebateStore((s) => s.errorMessage);
  const topic = useDebateStore((s) => s.topic);
  const activeSpeaker = useDebateStore((s) => s.activeSpeaker);
  const activeTurnId = useDebateStore((s) => s.activeTurnId);

  const focusOptions = useDebateStore((s) => s.focusOptions);
  const selectedFocusId = useDebateStore((s) => s.selectedFocusId);
  const intensityDraft = useDebateStore((s) => s.intensityDraft);
  const userContextDraft = useDebateStore((s) => s.userContextDraft);
  const isConfigurationReady = useDebateStore((s) => s.isConfigurationReady);
  const setSelectedFocus = useDebateStore((s) => s.setSelectedFocus);
  const setIntensityDraft = useDebateStore((s) => s.setIntensityDraft);
  const setUserContextDraft = useDebateStore((s) => s.setUserContextDraft);

  const [secondsLeft, setSecondsLeft] = useState(0);
  const [hoveredDebater, setHoveredDebater] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const prevPhaseRef = useRef(phase);

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

  useEffect(() => {
    if (phase === "complete" && prevPhaseRef.current !== "complete") {
      setTab("summary");
    }
    prevPhaseRef.current = phase;
  }, [phase, setTab]);

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
  const hoveredDebaterData = debaters.find((d) => d.id === hoveredDebater);
  const selectedFocus = focusOptions.find((option) => option.id === selectedFocusId);
  const recentActivities = activities.slice(-6).reverse();
  const summaryBackdrop = images.summary || images.background;

  const progressSteps = roomSteps.map((step) => {
    const currentOrder = phaseOrder[phase];
    const stepOrder = phaseOrder[step.key];

    if (phase === "error") {
      return { ...step, state: stepOrder <= currentOrder ? "error" : "pending" };
    }

    if (currentOrder > stepOrder) {
      return { ...step, state: "done" };
    }

    if (currentOrder === stepOrder) {
      return { ...step, state: "active" };
    }

    return { ...step, state: "pending" };
  });

  const handleDebaterPointer = (debaterId: string, clientX: number, clientY: number) => {
    setHoveredDebater(debaterId);
    setTooltipPos(clampTooltip(clientX, clientY));
  };

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
      {hoveredDebaterData && (
        <div
          className="debater-tooltip-fixed"
          style={{ left: tooltipPos.x, top: tooltipPos.y }}
        >
          <div className="debater-tooltip-header">
            {hoveredDebaterData.avatar_url ? (
              <img src={hoveredDebaterData.avatar_url} alt={hoveredDebaterData.name} className="tooltip-avatar" />
            ) : (
              <div className="tooltip-avatar-placeholder">
                {hoveredDebaterData.name.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div className="tooltip-title">
              <span className="tooltip-name">{hoveredDebaterData.name}</span>
              <span className="tooltip-personality">{hoveredDebaterData.personality}</span>
            </div>
          </div>

          <div className="debater-tooltip-body">
            <div className="tooltip-row">
              <span className="tooltip-label">背景</span>
              <span className="tooltip-value">{hoveredDebaterData.background}</span>
            </div>
            <div className="tooltip-row">
              <span className="tooltip-label">立场</span>
              <span className="tooltip-value">{hoveredDebaterData.stance}</span>
            </div>
            <div className="tooltip-row">
              <span className="tooltip-label">发言方式</span>
              <span className="tooltip-value">{hoveredDebaterData.speaking_style}</span>
            </div>
          </div>
        </div>
      )}

      <header className="room-header">
        <div className="room-brand">
          <span className="room-logo" aria-hidden="true">
            DR
          </span>
          <div className="room-brand-copy">
          <span className="room-title">DebateAI Room</span>
            <span className="room-subtitle">面向多智能体辩论的控制台工作台</span>
          </div>
        </div>

        <nav className="room-tabs" aria-label="Room sections">
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
          <div className="status-chip">
            <span className={`status-dot ${running ? "live" : ""}`} />
            <span>{phaseLabel}</span>
          </div>
          {running ? (
            <button className="stop-button" onClick={onStop}>
              结束本轮
            </button>
          ) : (
            <button className="sidebar-action primary" onClick={() => window.location.reload()}>
              开始新会话
            </button>
          )}
        </div>
      </header>

      <div className="room-topic-bar">
        <div>
          <span className="topic-bar-label">当前辩题</span>
          <p>{topic || "辩题待定"}</p>
        </div>
        <div className="topic-bar-meta">
          <span>会话 {sessionId ? sessionId.slice(0, 8) : "待生成"}</span>
          <span>{debaters.length} 位辩手</span>
          <span>{lines.length} 轮已完成</span>
        </div>
      </div>

      <div className="room-layout">
        <aside className="room-sidebar left">
          <section className="sidebar-panel">
            <div className="sidebar-panel-head">
              <h4>房间状态</h4>
              <span>{running ? "运行中" : "待命"}</span>
            </div>

            <Timer phase={phase} secondsLeft={secondsLeft} />

            <div className="sidebar-info-grid">
              <article className="sidebar-stat-card">
                <span>阶段</span>
                <strong>{phaseLabel}</strong>
              </article>
              <article className="sidebar-stat-card">
                <span>当前发言</span>
                <strong>{activeSpeaker || "主持人"}</strong>
              </article>
              <article className="sidebar-stat-card">
                <span>轮次</span>
                <strong>{activeTurnId !== null ? activeTurnId + 1 : "--"}</strong>
              </article>
              <article className="sidebar-stat-card">
                <span>计时</span>
                <strong>{secondsLeft > 0 ? formatTime(secondsLeft) : "--:--"}</strong>
              </article>
            </div>
          </section>

          <section className="sidebar-panel">
            <div className="sidebar-panel-head">
              <h4>辩手阵列</h4>
              <span>{debaters.length || 0}</span>
            </div>

            <div className="sidebar-debaters">
              {debaters.length === 0 ? (
                <p className="sidebar-empty">主持人完成准备后，辩手会出现在这里。</p>
              ) : (
                debaters.map((debater) => (
                  <button
                    key={debater.id}
                    type="button"
                    className={`sidebar-debater ${activeSpeaker === debater.name ? "is-active" : ""}`}
                    onMouseEnter={(e) => handleDebaterPointer(debater.id, e.clientX, e.clientY)}
                    onMouseMove={(e) => handleDebaterPointer(debater.id, e.clientX, e.clientY)}
                    onMouseLeave={() => setHoveredDebater(null)}
                  >
                    {debater.avatar_url ? (
                      <img src={debater.avatar_url} alt={debater.name} className="debater-thumb" />
                    ) : (
                      <div className="debater-thumb-placeholder">{debater.name.slice(0, 2).toUpperCase()}</div>
                    )}
                    <div className="debater-info">
                      <span className="debater-name">{debater.name}</span>
                      <span className="debater-stance">{debater.stance}</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="sidebar-panel">
            <div className="sidebar-panel-head">
              <h4>最近活动</h4>
              <span>{recentActivities.length}</span>
            </div>

            <div className="sidebar-activities">
              {recentActivities.length === 0 ? (
                <p className="sidebar-empty">运行开始后，过程事件会显示在这里。</p>
              ) : (
                recentActivities.map((activity) => (
                  <article key={activity.id} className={`sidebar-activity ${activity.tone}`}>
                    <div>
                      <span className="activity-title">{activity.title}</span>
                      {activity.detail && <p>{activity.detail}</p>}
                    </div>
                    <span className="activity-time">
                      {new Date(activity.at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </article>
                ))
              )}
            </div>
          </section>
        </aside>

        <main className="room-main">
          {errorMessage && <p className="error room-error">{errorMessage}</p>}

          {currentTab === "host" && (
            <div className="tab-content host-tab">
              <section className="workspace-section host-hero-section">
            <div className="workspace-hero-copy">
              <p className="eyebrow">主持人工作台</p>
              <h2>{phaseLabel}</h2>
              <p>{phaseDetail || "主持人正在准备这场辩论，并整理可供交锋的讨论框架。"}</p>
            </div>
            <div className="workspace-hero-metrics">
              <article>
                <span>当前切面</span>
                <strong>{selectedFocus?.name || "待选择"}</strong>
              </article>
              <article>
                <span>交锋强度</span>
                <strong>{intensityDraft}</strong>
              </article>
            </div>
              </section>

              <section className="workspace-section research-section">
                <header className="section-header">
                  <div>
                    <p className="eyebrow">调研流</p>
                    <h2>主持人调研笔记</h2>
                  </div>
                  <span className="phase-badge subtle">{phaseLabel}</span>
                </header>
                <div className="research-content">
                  {hostResearch ? (
                    <article className="markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{hostResearch}</ReactMarkdown>
                    </article>
                  ) : (
                    <div className="research-loading">
                      <div className="loading-spinner" />
                      <p>主持人正在收集背景信息、争议焦点和可能的讨论切面。</p>
                    </div>
                  )}
                </div>
              </section>

              {phase === "configuring" ? (
                <section className="workspace-section configuration-section">
                  <header className="section-header">
                    <div>
                      <p className="eyebrow">讨论切面</p>
                      <h2>选择本轮更关注的讨论切面</h2>
                    </div>
                  </header>

                  <div className="configuration-panel">
                    <p className="form-intro">
                      选择你更希望这场辩论重点展开的角度。这里决定的是讨论重点，而不是预设答案。
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

                    <div className="grid config-grid single-row">
                      <label className="field">
                        <span className="field-label">交锋强度</span>
                        <select
                          value={intensityDraft}
                          onChange={(e) => setIntensityDraft(e.target.value as "mild" | "balanced" | "intense")}
                        >
                          <option value="mild">Mild</option>
                          <option value="balanced">Balanced</option>
                          <option value="intense">Intense</option>
                        </select>
                      </label>
                    </div>

                    <label className="field">
                      <span className="field-label">补充背景</span>
                      <textarea
                        className="topic-textarea"
                        rows={4}
                        value={userContextDraft}
                        onChange={(e) => setUserContextDraft(e.target.value)}
                        placeholder="补充场景约束、现实条件或你掌握的背景信息。系统会把这些作为讨论背景，而不是你的立场。"
                      />
                    </label>

                    <div className="actions">
                      <button
                        type="button"
                        className="primary-button"
                        disabled={!canConfigure}
                        onClick={() => void handleConfigure()}
                      >
                        继续进入辩论
                      </button>
                    </div>
                  </div>
                </section>
              ) : selectedFocusId ? (
                <section className="workspace-section configuration-section">
                  <header className="section-header">
                    <div>
                      <p className="eyebrow">已锁定配置</p>
                      <h2>当前辩论配置</h2>
                    </div>
                  </header>

                  <div className="configuration-readonly">
                    <div className="config-item">
                      <span className="config-label">讨论切面</span>
                      <span className="config-value">{selectedFocus?.name || selectedFocusId}</span>
                    </div>
                    <div className="config-item">
                      <span className="config-label">交锋强度</span>
                      <span className="config-value">{intensityDraft}</span>
                    </div>
                    {userContextDraft && (
                      <div className="config-item">
                        <span className="config-label">补充背景</span>
                        <p className="config-text">{userContextDraft}</p>
                      </div>
                    )}
                  </div>
                </section>
              ) : null}

              <section className="workspace-section debaters-section">
                <header className="section-header">
                  <div>
                    <p className="eyebrow">辩手阵列</p>
                    <h2>辩手阵列</h2>
                  </div>
                </header>

                <div className="debaters-grid">
                  {debaters.length === 0 ? (
                    <div className="debaters-loading">
                      <div className="loading-spinner" />
                      <p>主持人完成配置后，辩手角色会在这里生成。</p>
                    </div>
                  ) : (
                    debaters.map((debater) => (
                      <article key={debater.id} className="debater-config-card">
                        <div className="debater-avatar-wrapper">
                          {debater.avatar_url ? (
                            <img src={debater.avatar_url} alt={debater.name} className="debater-avatar-img" />
                          ) : images.avatars[debater.name] ? (
                            <img src={images.avatars[debater.name]} alt={debater.name} className="debater-avatar-img" />
                          ) : (
                            <div className="debater-avatar-loading">{debater.name.slice(0, 2).toUpperCase()}</div>
                          )}
                        </div>
                        <div className="debater-config-info">
                          <h3>{debater.name}</h3>
                          <p className="debater-config-bg">{debater.background}</p>
                          <p className="debater-config-stance">{debater.stance}</p>
                          <p className="debater-config-style">{debater.speaking_style}</p>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </section>

              {images.background && (
                <section className="workspace-section scene-section">
                  <header className="section-header">
                    <div>
                      <p className="eyebrow">舞台场景</p>
                      <h2>辩论场景</h2>
                    </div>
                  </header>

                  <div className="scene-image-wrapper">
                    <img src={images.background} alt="辩论场景" className="scene-image" />
                  </div>
                </section>
              )}
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
                <section className="stage-header">
                  <div className="stage-header-copy">
                    <p className="eyebrow">辩论舞台</p>
                    <h2>{activeSpeaker ? `${activeSpeaker} 正在发言` : "辩论记录正在展开"}</h2>
                    <p>
                      {activeSpeaker && activeTurnId !== null
                        ? `当前是第 ${activeTurnId + 1} 轮，系统正在实时生成该辩手的发言内容。`
                        : "整场辩论会按阶段、按轮次实时更新，而不是一次性输出整篇结果。"}
                    </p>
                  </div>

                  <div className="stage-header-actions">
                    <Timer phase={phase} secondsLeft={secondsLeft} />
                    <div className="status-chip strong">
                      <span className={`status-dot ${running ? "live" : ""}`} />
                      <span>{phaseLabel}</span>
                    </div>
                  </div>
                </section>

                <DebateStream lines={mergedLines} />
              </div>
            </div>
          )}

          {currentTab === "summary" && (
            <div className="tab-content summary-tab">
              {summaryBackdrop && (
                <div className="summary-stage-bg">
                  <img src={summaryBackdrop} alt="辩论总结背景" className="summary-bg-image" />
                  <div className="summary-overlay" />
                </div>
              )}

              <div className="summary-stage-content">
              <section className="workspace-section summary-hero-section">
                <div className="workspace-hero-copy">
                  <p className="eyebrow">总结报告</p>
                  <h2>主持人综合判断与最终输出</h2>
                  <p>实时交锋结束后，整场辩论会被整理成一份更适合阅读和回看的报告。</p>
                </div>
              </section>

              <div className="summary-content">
                {images.summary && (
                  <div className="summary-poster">
                    <img src={images.summary} alt="辩论总结海报" />
                  </div>
                )}

                <div className="summary-report">
                  <header className="section-header">
                    <div>
                      <p className="eyebrow">Markdown 报告</p>
                      <h2>会话总结</h2>
                    </div>
                  </header>

                  {reportMarkdown ? (
                    <article className="markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{reportMarkdown}</ReactMarkdown>
                    </article>
                  ) : hostSummary ? (
                    <div className="summary-streaming markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{hostSummary}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="summary-loading">
                      <div className="loading-spinner" />
                      <p>主持人仍在整理最终报告。</p>
                    </div>
                  )}
                </div>
              </div>
              </div>
            </div>
          )}
        </main>

        <aside className="room-sidebar right">
          <section className="sidebar-panel">
            <div className="sidebar-panel-head">
              <h4>流程进度</h4>
              <span>{phase === "complete" ? "完成" : "运行中"}</span>
            </div>

            <ol className="progress-list">
              {progressSteps.map((step, index) => (
                <li key={step.label} className={`progress-item ${step.state}`}>
                  <span className="progress-index">{String(index + 1).padStart(2, "0")}</span>
                  <span>{step.label}</span>
                </li>
              ))}
            </ol>
          </section>

          <section className="sidebar-panel">
            <div className="sidebar-panel-head">
              <h4>快捷切换</h4>
              <span>视图</span>
            </div>

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
            </div>
          </section>

          <section className="sidebar-panel">
            <div className="sidebar-panel-head">
              <h4>辩题概览</h4>
              <span>{topic ? "已加载" : "待生成"}</span>
            </div>
            <div className="sidebar-brief">
              <p>{topic || "辩题暂未生成。"}</p>
              {phaseDetail && <p className="muted">{phaseDetail}</p>}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
