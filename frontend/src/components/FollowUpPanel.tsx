import { useState } from "react";
import { useDebateStore } from "../store/debateStore";
import { useFollowUp } from "../hooks/useFollowUp";

export function FollowUpPanel() {
  const [question, setQuestion] = useState("");
  const { followUpMessages, followUpTarget, debaters, isFollowUpStreaming, sessionId } =
    useDebateStore();
  const { submitFollowUp } = useFollowUp();

  const availableTargets = [
    { id: "host", name: "主持人", avatar: "🎙️" },
    ...debaters.map((d) => ({ id: d.name, name: d.name, avatar: d.avatar_emoji })),
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !followUpTarget || !sessionId || isFollowUpStreaming) return;

    await submitFollowUp({
      session_id: sessionId,
      target_role: followUpTarget,
      question: question.trim(),
    });
    setQuestion("");
  };

  return (
    <div className="follow-up-panel">
      <div className="follow-up-header">
        <h3>辩论后追问</h3>
        <p>选择主持人或任意辩手继续提问</p>
      </div>

      {/* Target Selector */}
      <div className="target-selector">
        {availableTargets.map((target) => (
          <button
            key={target.id}
            className={`target-button ${followUpTarget === target.id ? "active" : ""}`}
            onClick={() => !isFollowUpStreaming && useDebateStore.getState().setFollowUpTarget(target.id)}
            disabled={isFollowUpStreaming}
          >
            <span className="target-avatar">{target.avatar}</span>
            <span className="target-name">{target.name}</span>
          </button>
        ))}
      </div>

      {/* Message Thread */}
      <div className="follow-up-thread">
        {followUpMessages.map((msg) => (
          <div key={msg.id} className={`message ${msg.target_role === "host" ? "host" : "debater"}`}>
            <div className="message-header">
              <span className="message-target">
                {msg.target_role === "host" ? "🎙️ 主持人" : `🎭 ${msg.target_role}`}
              </span>
              <span className="message-time">
                {new Date(msg.created_at).toLocaleTimeString()}
              </span>
            </div>
            <div className="message-content">
              <div className="question">
                <strong>问：</strong>
                {msg.question}
              </div>
              <div className="response">
                <strong>答：</strong>
                {msg.response}
                {msg.isStreaming && <span className="streaming-indicator">▌</span>}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Input Form */}
      <form className="follow-up-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={
            followUpTarget
              ? `向 ${followUpTarget === "host" ? "主持人" : followUpTarget} 提问...`
              : "请先选择提问对象..."
          }
          disabled={!followUpTarget || isFollowUpStreaming}
          maxLength={500}
        />
        <button
          type="submit"
          disabled={!question.trim() || !followUpTarget || isFollowUpStreaming}
        >
          {isFollowUpStreaming ? "生成中..." : "发送"}
        </button>
      </form>
    </div>
  );
}
