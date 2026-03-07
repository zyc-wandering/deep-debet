import { DebaterConfig } from "../types";

interface Props {
  debater: DebaterConfig;
}

export function DebaterCard({ debater }: Props) {
  return (
    <article className="debater-card">
      <div className="debater-card-top">
        <span className="debater-index">Participant</span>
        <span className="debater-avatar" aria-hidden="true">
          {debater.avatar_emoji || "辩"}
        </span>
      </div>

      <div className="debater-head">
        <h3>{debater.name}</h3>
        <p className="muted">{debater.background}</p>
      </div>

      <dl className="debater-meta">
        <div>
          <dt>立场</dt>
          <dd>{debater.stance}</dd>
        </div>
        <div>
          <dt>风格</dt>
          <dd>{debater.personality}</dd>
        </div>
        <div>
          <dt>发言方式</dt>
          <dd>{debater.speaking_style}</dd>
        </div>
      </dl>
    </article>
  );
}
