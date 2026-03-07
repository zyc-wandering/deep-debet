import { useState } from "react";
import { DebateStartRequest } from "../types";

interface Props {
  onStart: (payload: DebateStartRequest) => void;
  isRunning: boolean;
}

export function ConfigPage({ onStart, isRunning }: Props) {
  const [topic, setTopic] = useState("AI生成内容是否应该强制标注");
  const [debaterCount, setDebaterCount] = useState(3);
  const [timeLimit, setTimeLimit] = useState(360);
  const [maxTurns, setMaxTurns] = useState(24);
  const [enableSearch, setEnableSearch] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim() || isRunning) return;

    onStart({
      topic: topic.trim(),
      debater_count: debaterCount,
      time_limit_sec: timeLimit,
      max_turns: maxTurns,
      enable_debater_search: enableSearch,
      fun_mode: "persona_clash",
    });
  };

  return (
    <div className="config-page">
      <header className="config-header">
        <p className="eyebrow">DebateAI Room</p>
        <h1>多 Agent AI 辩论室</h1>
        <p className="config-intro">
          输入一个富有争议性的命题，AI 主持人将调研背景、设计辩手，
          并引导一场多视角的深度辩论。
        </p>
      </header>

      <form className="config-form" onSubmit={handleSubmit}>
        <div className="form-section">
          <label className="field-label">辩题</label>
          <textarea
            className="topic-textarea"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="输入一个具体、有争议性的命题..."
            minLength={5}
            maxLength={240}
            required
            disabled={isRunning}
          />
          <p className="field-hint">建议格式：《陈述性命题》，如"AI生成内容是否应该强制标注"</p>
        </div>

        <div className="config-grid">
          <div className="form-field">
            <label className="field-label">辩手数量</label>
            <select
              value={debaterCount}
              onChange={(e) => setDebaterCount(Number(e.target.value))}
              disabled={isRunning}
            >
              <option value={2}>2 位</option>
              <option value={3}>3 位</option>
              <option value={4}>4 位</option>
              <option value={5}>5 位</option>
            </select>
          </div>

          <div className="form-field">
            <label className="field-label">时间限制</label>
            <select
              value={timeLimit}
              onChange={(e) => setTimeLimit(Number(e.target.value))}
              disabled={isRunning}
            >
              <option value={180}>3 分钟</option>
              <option value={360}>6 分钟</option>
              <option value={600}>10 分钟</option>
              <option value={900}>15 分钟</option>
            </select>
          </div>

          <div className="form-field">
            <label className="field-label">最大轮次</label>
            <select
              value={maxTurns}
              onChange={(e) => setMaxTurns(Number(e.target.value))}
              disabled={isRunning}
            >
              <option value={12}>12 轮</option>
              <option value={24}>24 轮</option>
              <option value={36}>36 轮</option>
              <option value={48}>48 轮</option>
            </select>
          </div>
        </div>

        <label className="toggle-field">
          <input
            type="checkbox"
            checked={enableSearch}
            onChange={(e) => setEnableSearch(e.target.checked)}
            disabled={isRunning}
          />
          <div>
            <span className="toggle-label">启用辩手实时搜索</span>
            <span className="field-hint">允许辩手在发言时搜索最新资料（可能增加 API 调用成本）</span>
          </div>
        </label>

        <div className="form-actions">
          <button
            type="submit"
            className="start-button"
            disabled={isRunning || !topic.trim()}
          >
            {isRunning ? "辩论进行中..." : "发起辩论"}
          </button>
        </div>
      </form>

      <div className="config-features">
        <h3>功能特性</h3>
        <div className="feature-grid">
          <div className="feature-card">
            <span className="feature-icon">🎭</span>
            <h4>AI 生成辩手</h4>
            <p>根据辩题自动生成立场各异、性格鲜明的 AI 辩手</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">🎨</span>
            <h4>AI 绘制场景</h4>
            <p>使用 Seedream 模型生成辩手头像与辩论场景</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">⚡</span>
            <h4>实时流式渲染</h4>
            <p>辩论过程逐字实时显示，增强临场感</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">📊</span>
            <h4>智能总结</h4>
            <p>辩论结束后自动生成结构化报告与可视化海报</p>
          </div>
        </div>
      </div>
    </div>
  );
}
