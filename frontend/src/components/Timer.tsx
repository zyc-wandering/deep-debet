import { DebatePhase } from "../types";

interface Props {
  phase: DebatePhase;
  secondsLeft: number;
}

const phaseText: Record<DebatePhase, string> = {
  idle: "待命",
  booting: "初始化",
  researching: "调研中",
  assembling: "配置中",
  debating: "辩论中",
  summarizing: "总结中",
  complete: "已完成",
  error: "异常",
};

export function Timer({ phase, secondsLeft }: Props) {
  const m = Math.floor(Math.max(0, secondsLeft) / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(Math.max(0, secondsLeft) % 60)
    .toString()
    .padStart(2, "0");

  return (
    <section className="timer">
      <div className="timer-label">
        <span className={`dot ${phase === "debating" ? "live" : ""}`} />
        <span>{phaseText[phase]}</span>
      </div>
      <strong>{phase === "debating" ? `${m}:${s}` : "--:--"}</strong>
    </section>
  );
}
