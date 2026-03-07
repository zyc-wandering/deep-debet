import { FormEvent, useState } from "react";
import { DebateStartRequest } from "../types";

interface Props {
  running: boolean;
  onStart: (payload: DebateStartRequest) => Promise<void>;
  onStop: () => Promise<void>;
}

export function TopicInput({ running, onStart, onStop }: Props) {
  const [topic, setTopic] = useState("AI 是否应该在高风险产品决策中替代人类判断？");
  const [debaterCount, setDebaterCount] = useState(3);
  const [timeLimitMinInput, setTimeLimitMinInput] = useState("6");
  const [maxTurnsInput, setMaxTurnsInput] = useState("24");
  const [enableDebaterSearch, setEnableDebaterSearch] = useState(false);

  const minTimeLimitMin = 2;
  const minTurns = debaterCount * 3;

  const sanitizeDigits = (value: string) => value.replace(/[^\d]/g, "");

  const normalizeTimeLimitMin = (raw: string) => {
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) {
      return minTimeLimitMin;
    }
    return Math.max(minTimeLimitMin, parsed);
  };

  const normalizeMaxTurns = (raw: string, currentDebaterCount: number) => {
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) {
      return currentDebaterCount * 3;
    }
    return Math.max(currentDebaterCount * 3, parsed);
  };

  const commitTimeLimitMin = () => {
    setTimeLimitMinInput(String(normalizeTimeLimitMin(timeLimitMinInput)));
  };

  const commitMaxTurns = (nextDebaterCount = debaterCount) => {
    setMaxTurnsInput(String(normalizeMaxTurns(maxTurnsInput, nextDebaterCount)));
  };

  const handleStart = async (e: FormEvent) => {
    e.preventDefault();
    const timeLimitMin = normalizeTimeLimitMin(timeLimitMinInput);
    const maxTurns = normalizeMaxTurns(maxTurnsInput, debaterCount);
    setTimeLimitMinInput(String(timeLimitMin));
    setMaxTurnsInput(String(maxTurns));
    await onStart({
      topic,
      debater_count: debaterCount,
      time_limit_sec: timeLimitMin * 60,
      max_turns: maxTurns,
      enable_debater_search: enableDebaterSearch,
      fun_mode: "persona_clash",
    });
  };

  return (
    <form className="topic-form" onSubmit={handleStart}>
      <div className="section-head">
        <div>
          <p className="eyebrow">New Session</p>
          <h2>发起一场新的多代理辩论</h2>
        </div>
        <p className="muted form-status">{running ? "进行中，参数已锁定" : "待命，可调整参数"}</p>
      </div>

      <p className="form-intro">
        写一个足够具体、又允许多方推演的命题。主持人会先调研，再为不同立场配置辩手。
      </p>

      <label className="field">
        <span className="field-label">辩题命题</span>
        <textarea
          className="topic-textarea"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          rows={4}
          disabled={running}
          placeholder="例如：AI 是否应该在高风险产品决策中替代人类判断？"
        />
      </label>

      <div className="grid config-grid">
        <label className="field">
          <span className="field-label">辩手数量</span>
          <select
            value={debaterCount}
            onChange={(e) => {
              const nextCount = Number(e.target.value);
              setDebaterCount(nextCount);
              setMaxTurnsInput((current) => String(normalizeMaxTurns(current, nextCount)));
            }}
            disabled={running}
          >
            {[2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n} 位
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field-label">时长上限（分钟）</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={timeLimitMinInput}
            onChange={(e) => setTimeLimitMinInput(sanitizeDigits(e.target.value))}
            onBlur={commitTimeLimitMin}
            disabled={running}
            aria-label="时长上限（分钟）"
          />
          <p className="field-hint">最短 2 分钟</p>
        </label>

        <label className="field">
          <span className="field-label">最大发言轮次</span>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={maxTurnsInput}
            onChange={(e) => setMaxTurnsInput(sanitizeDigits(e.target.value))}
            onBlur={() => commitMaxTurns()}
            disabled={running}
            aria-label="最大发言轮次"
          />
          <p className="field-hint">最少为当前辩手数量的 3 倍，当前最小值 {minTurns}</p>
        </label>
      </div>

      <label className="toggle">
        <input
          type="checkbox"
          checked={enableDebaterSearch}
          onChange={(e) => setEnableDebaterSearch(e.target.checked)}
          disabled={running}
        />
        <div>
          <span className="field-label">允许辩手实时搜索</span>
          <p className="muted">开启后，辩手可在发言阶段补充最新外部信息。</p>
        </div>
      </label>

      <div className="actions">
        <button type="submit" className="primary-button" disabled={running || topic.trim().length < 5}>
          开始辩论
        </button>
        <button type="button" className="ghost-button" disabled={!running} onClick={() => onStop()}>
          请求停止
        </button>
      </div>

      <p className="form-footnote">
        提前停止不会直接断开本轮流程，系统仍会等待主持人输出总结与报告。
      </p>
    </form>
  );
}
