import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  Phase,
  DebateLine,
  DebateLanguage,
  DebaterConfig,
  FollowUpMessage,
  FocusOption,
  StructuredReport,
  TranscriptMessage,
} from "../types";

export type RunStatus = "idle" | "running" | "done" | "error";

interface SessionState {
  phase: Phase;
  status: RunStatus;
  topic: string;
  debateLanguage: DebateLanguage;
  sessionId: string;
  debateDeadlineMs: number | null;

  hostResearch: string;
  focusOptions: FocusOption[];
  selectedFocusId: string;
  intensityDraft: "mild" | "balanced" | "intense";
  userContextDraft: string;
  isConfigurationReady: boolean;

  debaters: DebaterConfig[];
  substituteDebaters: DebaterConfig[];

  hostSummary: string;
  lines: DebateLine[];
  currentStage: string | null;
  transcript: TranscriptMessage[];

  reportPath: string;
  reportMarkdown: string;
  structuredReport: StructuredReport | null;

  followUpMessages: FollowUpMessage[];

  setPhase(phase: Phase): void;
  reset(): void;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      phase: "config",
      status: "idle",
      topic: "",
      debateLanguage: "zh",
      sessionId: "",
      debateDeadlineMs: null,

      hostResearch: "",
      focusOptions: [],
      selectedFocusId: "",
      intensityDraft: "balanced",
      userContextDraft: "",
      isConfigurationReady: false,

      debaters: [],
      substituteDebaters: [],

      hostSummary: "",
      lines: [],
      currentStage: null,
      transcript: [],

      reportPath: "",
      reportMarkdown: "",
      structuredReport: null,

      followUpMessages: [],

      setPhase: (phase) => set({ phase }),
      reset: () =>
        set({
          phase: "config",
          status: "idle",
          topic: "",
          debateLanguage: "zh",
          sessionId: "",
          debateDeadlineMs: null,
          hostResearch: "",
          focusOptions: [],
          selectedFocusId: "",
          intensityDraft: "balanced",
          userContextDraft: "",
          isConfigurationReady: false,
          debaters: [],
          substituteDebaters: [],
          hostSummary: "",
          lines: [],
          currentStage: null,
          transcript: [],
          reportPath: "",
          reportMarkdown: "",
          structuredReport: null,
          followUpMessages: [],
        }),
    }),
    {
      name: "debate-session",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        phase: state.phase,
        status: state.status,
        topic: state.topic,
        debateLanguage: state.debateLanguage,
        sessionId: state.sessionId,
        debateDeadlineMs: state.debateDeadlineMs,
        hostResearch: state.hostResearch,
        focusOptions: state.focusOptions,
        selectedFocusId: state.selectedFocusId,
        intensityDraft: state.intensityDraft,
        userContextDraft: state.userContextDraft,
        isConfigurationReady: state.isConfigurationReady,
        debaters: state.debaters,
        substituteDebaters: state.substituteDebaters,
        hostSummary: state.hostSummary,
        lines: state.lines,
        currentStage: state.currentStage,
        transcript: state.transcript,
        reportPath: state.reportPath,
        reportMarkdown: state.reportMarkdown,
        structuredReport: state.structuredReport,
        followUpMessages: state.followUpMessages,
      }),
    },
  ),
);
