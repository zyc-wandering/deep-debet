import { FormEvent, useState } from "react";
import { DebateStartRequest } from "../types";

interface Props {
  running: boolean;
  onStart: (payload: DebateStartRequest) => Promise<void>;
  onStop: () => Promise<void>;
}

export function TopicInput({ running, onStart, onStop }: Props) {
  const [topic, setTopic] = useState("AI 是否应该在产品决策中替代人类判断？");
  const [debaterCount, setDebaterCount] = useState(3);
  const [timeLimitSec, setTimeLimitSec] = useState(360);
  const [maxTurns, setMaxTurns] = useState(24);
  const [enableDebaterSearch, setEnableDebaterSearch] = useState(false);

  const handleStart = async (e: FormEvent) => {
    e.preventDefault();
    await onStart({
      topic,
      debater_count: debaterCount,
      time_limit_sec: timeLimitSec,
      max_turns: maxTurns,
      enable_debater_search: enableDebaterSearch,
      fun_mode: "persona_clash",
    });
  };

  return (
    <form className="topic-form" onSubmit={handleStart}>
      <label className="label">辩题</label>
      <textarea
        className="topic-textarea"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        rows={3}
        disabled={running}
      />

      <div className="grid">
        <label>
          辩手数量
          <select
            value={debaterCount}
            onChange={(e) => setDebaterCount(Number(e.target.value))}
            disabled={running}
          >
            {[2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        <label>
          时间上限(秒)
          <input
            type="number"
            min={60}
            max={1800}
            value={timeLimitSec}
            onChange={(e) => setTimeLimitSec(Number(e.target.value))}
            disabled={running}
          />
        </label>

        <label>
          最大发言轮次
          <input
            type="number"
            min={4}
            max={80}
            value={maxTurns}
            onChange={(e) => setMaxTurns(Number(e.target.value))}
            disabled={running}
          />
        </label>
      </div>

      <label className="checkbox">
        <input
          type="checkbox"
          checked={enableDebaterSearch}
          onChange={(e) => setEnableDebaterSearch(e.target.checked)}
          disabled={running}
        />
        辩手允许实时搜索
      </label>

      <div className="actions">
        <button type="submit" disabled={running || topic.trim().length < 5}>
          开始辩论
        </button>
        <button type="button" className="ghost" disabled={!running} onClick={() => onStop()}>
          停止
        </button>
      </div>
    </form>
  );
}

