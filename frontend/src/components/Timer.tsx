interface Props {
  running: boolean;
  secondsLeft: number;
}

export function Timer({ running, secondsLeft }: Props) {
  const m = Math.floor(Math.max(0, secondsLeft) / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(Math.max(0, secondsLeft) % 60)
    .toString()
    .padStart(2, "0");

  return (
    <section className="timer">
      <span className={running ? "dot live" : "dot"} />
      <span>{running ? "进行中" : "未开始"}</span>
      <strong>
        {m}:{s}
      </strong>
    </section>
  );
}

