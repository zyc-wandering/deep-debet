import { create } from "zustand";
import { DebateLine, DebaterConfig } from "../types";

type RunStatus = "idle" | "running" | "done" | "error";

interface DebateState {
  status: RunStatus;
  sessionId: string;
  debateDeadlineMs: number | null;
  hostResearch: string;
  hostSummary: string;
  debaters: DebaterConfig[];
  lines: DebateLine[];
  liveBuffers: Record<string, string>;
  reportPath: string;
  reportMarkdown: string;
  errorMessage: string;

  start(): void;
  appendHostResearch(chunk: string): void;
  setDebaters(sessionId: string, debaters: DebaterConfig[], debateDeadlineMs: number | null): void;
  appendToken(sessionId: string, speaker: string, turnId: number, token: string): void;
  finalizeTurn(sessionId: string, speaker: string, turnId: number, fullContent: string): void;
  appendHostSummary(chunk: string): void;
  setDone(sessionId: string, reportPath: string): void;
  setReportMarkdown(text: string): void;
  setError(msg: string): void;
  reset(): void;
}

const initialState = {
  status: "idle" as RunStatus,
  sessionId: "",
  debateDeadlineMs: null as number | null,
  hostResearch: "",
  hostSummary: "",
  debaters: [],
  lines: [],
  liveBuffers: {},
  reportPath: "",
  reportMarkdown: "",
  errorMessage: "",
};

export const useDebateStore = create<DebateState>((set, get) => ({
  ...initialState,
  start: () =>
    set({
      ...initialState,
      status: "running",
    }),
  appendHostResearch: (chunk) =>
    set((s) => ({
      hostResearch: s.hostResearch + chunk,
    })),
  setDebaters: (sessionId, debaters, debateDeadlineMs) =>
    set(() => ({
      sessionId,
      debateDeadlineMs,
      debaters,
    })),
  appendToken: (sessionId, speaker, turnId, token) => {
    const key = `${speaker}-${turnId}`;
    set((s) => ({
      sessionId: s.sessionId || sessionId,
      liveBuffers: {
        ...s.liveBuffers,
        [key]: (s.liveBuffers[key] || "") + token,
      },
    }));
  },
  finalizeTurn: (sessionId, speaker, turnId, fullContent) => {
    const key = `${speaker}-${turnId}`;
    set((s) => {
      const nextBuffers = { ...s.liveBuffers };
      delete nextBuffers[key];
      return {
        sessionId: s.sessionId || sessionId,
        liveBuffers: nextBuffers,
        lines: [...s.lines, { key, speaker, turnId, content: fullContent }],
      };
    });
  },
  appendHostSummary: (chunk) =>
    set((s) => ({
      hostSummary: s.hostSummary + chunk,
    })),
  setDone: (sessionId, reportPath) =>
    set({
      status: "done",
      sessionId,
      reportPath,
    }),
  setReportMarkdown: (text) => set({ reportMarkdown: text }),
  setError: (msg) =>
    set({
      status: "error",
      errorMessage: msg,
    }),
  reset: () => set({ ...initialState }),
}));

export const selectLiveLines = (): DebateLine[] => {
  const state = useDebateStore.getState();
  const buffered: DebateLine[] = Object.entries(state.liveBuffers).map(([key, content]) => {
    const [speaker, turnIdRaw] = key.split("-");
    return { key, speaker, content, turnId: Number(turnIdRaw || 0) };
  });
  return [...state.lines, ...buffered].sort((a, b) => a.turnId - b.turnId);
};
