import { DebatePhase } from "../types";

interface Props {
  phase: DebatePhase;
  secondsLeft: number;
}

const phaseText: Record<DebatePhase, string> = {
  idle: "Idle",
  booting: "Booting",
  researching: "Researching",
  assembling: "Assembling",
  generating_background: "Generating scene",
  configuring: "Configuring",
  opening: "Opening",
  free_debate: "Free debate",
  closing: "Closing",
  summarizing: "Summarizing",
  generating_summary_image: "Generating poster",
  complete: "Complete",
  follow_up: "Follow-up",
  error: "Error",
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
        <span>{phaseText[phase]}</span>
      </div>
      <strong>{showTimer ? `${m}:${s}` : "--:--"}</strong>
    </section>
  );
}
