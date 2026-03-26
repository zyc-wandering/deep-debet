import type { DebaterConfig, DebateLine, TranscriptMessage } from "../types";

interface TranscriptData {
  topic: string;
  debaters: DebaterConfig[];
  stageLines: Record<string, DebateLine[]>;
  transcript: TranscriptMessage[];
  isZh: boolean;
}

export function generateTranscriptMarkdown({
  topic,
  debaters,
  stageLines,
  transcript,
  isZh,
}: TranscriptData): string {
  const lines: string[] = [];

  // Title
  lines.push(`# ${isZh ? "辩论记录" : "Debate Transcript"}: ${topic}`);
  lines.push("");

  // Debater roster
  lines.push(`## ${isZh ? "辩手阵容" : "Debater Roster"}`);
  lines.push("");
  lines.push(
    isZh
      ? "| 辩手 | 立场 | 背景 |"
      : "| Debater | Stance | Background |",
  );
  lines.push("|------|------|------|");
  for (const d of debaters) {
    lines.push(`| ${d.name} | ${d.stance} | ${d.background} |`);
  }
  lines.push("");

  // Helper to find debater stance
  const stanceOf = (speaker: string) =>
    debaters.find((d) => d.name === speaker)?.stance ?? "";

  // Stage sections
  const stages: { key: string; zhLabel: string; enLabel: string }[] = [
    { key: "opening", zhLabel: "开场陈述", enLabel: "Opening Statements" },
    { key: "free_debate", zhLabel: "自由辩论", enLabel: "Free Debate" },
    { key: "closing", zhLabel: "总结陈词", enLabel: "Closing Statements" },
  ];

  for (const stage of stages) {
    const entries = stageLines[stage.key];
    if (!entries || entries.length === 0) {
      // Fall back to transcript filtered by stage
      const fromTranscript = transcript.filter((t) => t.stage === stage.key);
      if (fromTranscript.length === 0) continue;

      lines.push(`## ${isZh ? stage.zhLabel : stage.enLabel}`);
      lines.push("");

      let roundNum = 0;
      for (const msg of fromTranscript) {
        roundNum++;
        const stance = stanceOf(msg.speaker);
        if (stage.key === "free_debate") {
          lines.push(`### Round ${roundNum} - ${msg.speaker}${stance ? ` (${stance})` : ""}`);
        } else {
          lines.push(`### ${msg.speaker}${stance ? ` (${stance})` : ""}`);
        }
        lines.push("");
        lines.push(msg.content);
        lines.push("");
      }
    } else {
      lines.push(`## ${isZh ? stage.zhLabel : stage.enLabel}`);
      lines.push("");

      let roundNum = 0;
      for (const entry of entries) {
        roundNum++;
        const stance = stanceOf(entry.speaker);
        if (stage.key === "free_debate") {
          lines.push(`### Round ${roundNum} - ${entry.speaker}${stance ? ` (${stance})` : ""}`);
        } else {
          lines.push(`### ${entry.speaker}${stance ? ` (${stance})` : ""}`);
        }
        lines.push("");
        lines.push(entry.content);
        lines.push("");
      }
    }
  }

  return lines.join("\n");
}
