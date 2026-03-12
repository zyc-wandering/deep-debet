import { DebatePhase } from "../types";

interface Props {
  phase: DebatePhase;
  secondsLeft: number;
}

const phaseText: Record<DebatePhase, string> = {
  idle: "待命",
  booting: "初始化",
  researching: "调研中",
  assembling: "组局中",
  generating_background: "生成场景",
  configuring: "配置中",
  opening: "开场陈述",
  free_debate: "自由辩论",
  closing: "总结陈词",
  summarizing: "总结中",
  generating_summary_image: "生成海报",
  complete: "已完成",
  follow_up: "追问中",
  error: "异常",
};

function isTimedPhase(phase: DebatePhase): boolean {
  return phase === "opening" || phase === "free_debate" || phase === "closing";
}

export function Timer({ phase, secondsLeft }: Props) {
  const showTimer = isTimedPhase(phase);
  const m = Math.floor(Math.max(0, secondsLeft) / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(Math.max(0, secondsLeft) % 60)
    .toString()
    .padStart(2, "0");

  return (
    <section className="timer">
      <div className="timer-label">
        <span className={`dot ${showTimer ? "live" : ""}`} />
        <div className="timer-copy">
          <span className="timer-phase">{phaseText[phase]}</span>
          <span className="timer-caption">{showTimer ? "当前阶段正在计时" : "计时将在正式辩论阶段开始"}</span>
        </div>
      </div>
      <strong className="timer-value">{showTimer ? `${m}:${s}` : "--:--"}</strong>
    </section>
  );
}
