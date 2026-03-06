import { DebaterConfig } from "../types";

interface Props {
  debater: DebaterConfig;
}

export function DebaterCard({ debater }: Props) {
  return (
    <article className="debater-card">
      <div className="debater-head">
        <span className="emoji">{debater.avatar_emoji || "🎙️"}</span>
        <h3>{debater.name}</h3>
      </div>
      <p className="muted">{debater.background}</p>
      <p className="stance">立场：{debater.stance}</p>
      <p className="personality">风格：{debater.personality}</p>
    </article>
  );
}

