import { create } from "zustand";
import { DebateLine, DebaterConfig, DebatePhase, WorkflowActivity } from "../types";

type RunStatus = "idle" | "running" | "done" | "error";

interface DebateState {
  status: RunStatus;
  phase: DebatePhase;
  phaseLabel: string;
  phaseDetail: string;
  topic: string;
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
  activities: WorkflowActivity[];
  activeSpeaker: string;
  activeTurnId: number | null;

  start(topic: string): void;
  setSessionId(sessionId: string): void;
  setPhase(phase: DebatePhase, label: string, detail?: string): void;
  addActivity(title: string, detail?: string, tone?: WorkflowActivity["tone"]): void;
  appendHostResearch(chunk: string): void;
  setDebaters(sessionId: string, debaters: DebaterConfig[], debateDeadlineMs: number | null): void;
  appendToken(sessionId: string, speaker: string, turnId: number, token: string): void;
  finalizeTurn(sessionId: string, speaker: string, turnId: number, fullContent: string): void;
  appendHostSummary(chunk: string): void;
  markStopRequested(): void;
  setDone(sessionId: string, reportPath: string): void;
  setReportMarkdown(text: string): void;
  setError(msg: string): void;
  reset(): void;
}

const makeActivity = (
  title: string,
  detail = "",
  tone: WorkflowActivity["tone"] = "neutral",
): WorkflowActivity => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  title,
  detail,
  tone,
  at: Date.now(),
});

const pushActivity = (
  current: WorkflowActivity[],
  title: string,
  detail = "",
  tone: WorkflowActivity["tone"] = "neutral",
): WorkflowActivity[] => {
  const nextItem = makeActivity(title, detail, tone);
  const last = current[current.length - 1];
  if (last && last.title === title && last.detail === detail && last.tone === tone) {
    return current;
  }
  return [...current.slice(-11), nextItem];
};

const initialState = {
  status: "idle" as RunStatus,
  phase: "idle" as DebatePhase,
  phaseLabel: "准备开始",
  phaseDetail: "输入一个具体命题后即可发起辩论。",
  topic: "",
  sessionId: "",
  debateDeadlineMs: null as number | null,
  hostResearch: "",
  hostSummary: "",
  debaters: [] as DebaterConfig[],
  lines: [] as DebateLine[],
  liveBuffers: {} as Record<string, string>,
  reportPath: "",
  reportMarkdown: "",
  errorMessage: "",
  activities: [] as WorkflowActivity[],
  activeSpeaker: "",
  activeTurnId: null as number | null,
};

export const useDebateStore = create<DebateState>((set) => ({
  ...initialState,
  start: (topic) =>
    set({
      ...initialState,
      topic,
      status: "running",
      phase: "booting",
      phaseLabel: "辩题已提交",
      phaseDetail: "正在建立会话并准备主持人工作流。",
      activities: [
        makeActivity("已提交新辩题", "系统已接收参数，准备开始主持人调研。", "live"),
      ],
    }),
  setSessionId: (sessionId) =>
    set((s) => ({
      sessionId: s.sessionId || sessionId,
    })),
  setPhase: (phase, label, detail = "") =>
    set((s) => ({
      phase,
      phaseLabel: label,
      phaseDetail: detail,
      activities: pushActivity(s.activities, label, detail, phase === "error" ? "error" : "live"),
    })),
  addActivity: (title, detail = "", tone = "neutral") =>
    set((s) => ({
      activities: pushActivity(s.activities, title, detail, tone),
    })),
  appendHostResearch: (chunk) =>
    set((s) => ({
      hostResearch: s.hostResearch + chunk,
    })),
  setDebaters: (sessionId, debaters, debateDeadlineMs) =>
    set((s) => ({
      sessionId: s.sessionId || sessionId,
      debateDeadlineMs,
      debaters,
      activities: pushActivity(
        s.activities,
        "辩手阵列已建立",
        `已生成 ${debaters.length} 位立场各异的辩手，倒计时开始。`,
        "done",
      ),
    })),
  appendToken: (sessionId, speaker, turnId, token) => {
    const key = `${speaker}-${turnId}`;
    set((s) => {
      const firstTokenOfTurn = !s.liveBuffers[key];
      return {
        sessionId: s.sessionId || sessionId,
        activeSpeaker: speaker,
        activeTurnId: turnId,
        liveBuffers: {
          ...s.liveBuffers,
          [key]: (s.liveBuffers[key] || "") + token,
        },
        activities: firstTokenOfTurn
          ? pushActivity(
              s.activities,
              `${speaker} 开始发言`,
              `第 ${turnId + 1} 轮正在实时生成中。`,
              "live",
            )
          : s.activities,
      };
    });
  },
  finalizeTurn: (sessionId, speaker, turnId, fullContent) => {
    const key = `${speaker}-${turnId}`;
    set((s) => {
      const nextBuffers = { ...s.liveBuffers };
      delete nextBuffers[key];
      return {
        sessionId: s.sessionId || sessionId,
        activeSpeaker: s.activeSpeaker === speaker && s.activeTurnId === turnId ? "" : s.activeSpeaker,
        activeTurnId: s.activeSpeaker === speaker && s.activeTurnId === turnId ? null : s.activeTurnId,
        liveBuffers: nextBuffers,
        lines: [...s.lines, { key, speaker, turnId, content: fullContent }],
        activities: pushActivity(
          s.activities,
          `${speaker} 完成发言`,
          `第 ${turnId + 1} 轮已写入辩论记录。`,
          "done",
        ),
      };
    });
  },
  appendHostSummary: (chunk) =>
    set((s) => ({
      hostSummary: s.hostSummary + chunk,
    })),
  markStopRequested: () =>
    set((s) => ({
      activities: pushActivity(
        s.activities,
        "已请求提前结束",
        "当前轮次结束后将进入主持人总结，不会中断已生成内容。",
        "neutral",
      ),
    })),
  setDone: (sessionId, reportPath) =>
    set((s) => ({
      status: "done",
      phase: "complete",
      phaseLabel: "报告已生成",
      phaseDetail: "主持人总结完成，本轮辩论已归档。",
      sessionId,
      reportPath,
      activeSpeaker: "",
      activeTurnId: null,
      activities: pushActivity(
        s.activities,
        "本轮辩论已完成",
        "可继续阅读报告，或调整参数发起下一轮辩论。",
        "done",
      ),
    })),
  setReportMarkdown: (text) => set({ reportMarkdown: text }),
  setError: (msg) =>
    set((s) => ({
      status: "error",
      phase: "error",
      phaseLabel: "流程异常",
      phaseDetail: msg,
      errorMessage: msg,
      activities: pushActivity(s.activities, "发生错误", msg, "error"),
    })),
  reset: () => set({ ...initialState }),
}));
