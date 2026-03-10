export type DebateEventType =
  | "phase"
  | "host_research"
  | "dimensions_extracted" // Host extracted focus dimensions
  | "debaters_ready"
  | "background_ready"
  | "avatars_ready"
  | "stage_change" // Debate stage changed (opening/free/closing)
  | "debate_token"
  | "debate_turn_end"
  | "host_summary"
  | "structured_report" // Structured report data available
  | "follow_up_token" // Follow-up response streaming
  | "follow_up_end" // Follow-up response complete
  | "done"
  | "error";

export type DebatePhase =
  | "idle"
  | "booting"
  | "researching"
  | "assembling"
  | "generating_background"
  | "configuring" // Pre-debate configuration
  | "opening" // Opening statements
  | "free_debate" // Main debate
  | "closing" // Closing statements
  | "summarizing"
  | "generating_summary_image"
  | "complete"
  | "follow_up" // Post-debate Q&A
  | "error";

// Explicit debate stages for structured debate flow
export type DebateStage = "opening" | "free_debate" | "closing" | "summary";

export type DebateRoomTab = "config" | "host" | "debate" | "summary";

export interface DebaterConfig {
  id: string;
  name: string;
  background: string;
  stance: string;
  personality: string;
  speaking_style: string;
  avatar_emoji: string;
  avatar_url?: string;
}

// Focus dimension for pre-debate configuration
export interface FocusDimension {
  id: string;
  name: string;
  description: string;
  selected: boolean;
}

// Pre-debate configuration
export interface PreDebateConfig {
  dimensions: FocusDimension[];
  intensity: "mild" | "balanced" | "intense";
  user_context: string;
}

// Follow-up message in post-debate Q&A
export interface FollowUpMessage {
  id: string;
  target_role: string; // "host" or debater name
  question: string;
  response: string;
  created_at: string;
  isStreaming?: boolean;
}

// Argument node for structured report
export interface ArgumentNode {
  id: string;
  speaker: string;
  content: string;
  turn_index: number;
  targets: string[]; // IDs of nodes this responds to
  status: "claim" | "support" | "attack" | "concession";
  focal_point?: string;
}

// Structured report data
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

export interface DebateImages {
  background?: string;
  summary?: string;
  avatars: Record<string, string>;
}

export interface DebateLine {
  key: string;
  speaker: string;
  content: string;
  turnId: number;
  isLive?: boolean;
  stage?: DebateStage; // Which debate stage this line belongs to
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
  // Pre-debate configuration (optional - set after research)
  pre_debate_config?: PreDebateConfig;
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
