export type DebateEventType =
  | "phase"
  | "host_research"
  | "debaters_ready"
  | "debate_token"
  | "debate_turn_end"
  | "host_summary"
  | "done"
  | "error";

export type DebatePhase =
  | "idle"
  | "booting"
  | "researching"
  | "assembling"
  | "debating"
  | "summarizing"
  | "complete"
  | "error";

export interface DebaterConfig {
  id: string;
  name: string;
  background: string;
  stance: string;
  personality: string;
  speaking_style: string;
  avatar_emoji: string;
}

export interface DebateLine {
  key: string;
  speaker: string;
  content: string;
  turnId: number;
  isLive?: boolean;
}

export interface WorkflowActivity {
  id: string;
  title: string;
  detail: string;
  tone: "neutral" | "live" | "done" | "error";
  at: number;
}

export interface DebateStartRequest {
  topic: string;
  debater_count: number;
  time_limit_sec: number;
  max_turns: number;
  enable_debater_search: boolean;
  fun_mode: "persona_clash";
}
