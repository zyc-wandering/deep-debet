/* ── UI Phase (5-phase flow) ── */
export type Phase = "config" | "research" | "drafting" | "arena" | "summary";

/* ── Backend phases (SSE "phase" event) ── */
export type DebatePhase =
  | "idle"
  | "booting"
  | "researching"
  | "configuring"
  | "assembling"
  | "generating_background"
  | "opening"
  | "free_debate"
  | "closing"
  | "summarizing"
  | "generating_summary_image"
  | "complete"
  | "follow_up"
  | "error";

export type DebateStage = "opening" | "free_debate" | "closing" | "summary";
export type DebateLanguage = "zh" | "en";

/* ── Backend data models ── */
export interface DebaterConfig {
  id: string;
  name: string;
  age: string;
  ethnicity: string;
  background: string;
  stance: string;
  personality: string;
  speaking_style: string;
  avatar_emoji: string;
  avatar_url?: string;
}

export interface FocusOption {
  id: string;
  name: string;
  description: string;
}

export interface PreDebateConfig {
  selected_focus_id: string;
  intensity: "mild" | "balanced" | "intense";
  user_context: string;
}

export interface FollowUpMessage {
  id: string;
  target_role: string;
  question: string;
  response: string;
  created_at: string;
  isStreaming?: boolean;
}

export interface ArgumentNode {
  id: string;
  speaker: string;
  content: string;
  turn_index: number;
  targets: string[];
  status: "claim" | "support" | "attack" | "concession";
  focal_point?: string;
}

export interface StructuredReport {
  background_summary: string;
  core_arguments: Array<{
    speaker: string;
    stance: string;
    key_points: string[];
  }>;
  clash_points: Array<{
    topic: string;
    positions: Record<string, string>;
  }>;
  synthesis: string;
  host_conclusion: string;
  argument_nodes: ArgumentNode[];
}

export interface DebateLine {
  key: string;
  speaker: string;
  content: string;
  turnId: number;
  isLive?: boolean;
  stage?: DebateStage;
}

export interface PreparingTurn {
  speaker: string;
  turnId: number;
  stage?: DebateStage;
}

export interface WorkflowActivity {
  id: string;
  title: string;
  detail: string;
  tone: "neutral" | "live" | "done" | "error";
  at: number;
}

/* ── API request/response types ── */
export interface DebateStartRequest {
  topic: string;
  debater_count: number;
  time_limit_sec: number;
  max_turns: number;
  enable_debater_search: boolean;
  debate_language: DebateLanguage;
  model_variant: "lite" | "pro";
  fun_mode: "persona_clash";
}

export interface DebateConfigureRequest {
  session_id: string;
  pre_debate_config: PreDebateConfig;
}

export interface FollowUpRequest {
  session_id: string;
  target_role: string;
  question: string;
}

/* ── UI-only config (ConfigPhase form state) ── */
export interface DebateConfig {
  topic: string;
  language: DebateLanguage;
  numDebaters: number;
  maxRounds: number;
  modelVariant: "lite" | "pro";
  enableSearch: boolean;
}

/* ── Arena transcript message ── */
export interface TranscriptMessage {
  id: string;
  timestamp: Date;
  speaker: string;
  content: string;
  stage: DebateStage;
  turnId: number;
}
