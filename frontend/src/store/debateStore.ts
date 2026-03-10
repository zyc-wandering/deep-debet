import { create } from "zustand";
import {
  DebateImages,
  DebateLine,
  DebaterConfig,
  DebatePhase,
  DebateRoomTab,
  DebateStage,
  FollowUpMessage,
  FocusOption,
  WorkflowActivity,
} from "../types";

type RunStatus = "idle" | "running" | "done" | "error";

interface DebateState {
  // Page navigation
  currentTab: DebateRoomTab;

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

  // Stage tracking
  currentStage: DebateStage | null;
  stageLines: Record<DebateStage, DebateLine[]>;

  // Images
  images: DebateImages;

  // Phase 3 configuration
  focusOptions: FocusOption[];
  selectedFocusId: string;
  intensityDraft: "mild" | "balanced" | "intense";
  userContextDraft: string;
  isConfigurationReady: boolean;

  // Follow-up
  followUpMessages: FollowUpMessage[];
  followUpLiveResponse: string;
  followUpTarget: string | null;
  isFollowUpStreaming: boolean;

  // Navigation
  setTab(tab: DebateRoomTab): void;

  // Debate actions
  start(topic: string): void;
  setSessionId(sessionId: string): void;
  setPhase(phase: DebatePhase, label: string, detail?: string): void;
  setStage(stage: DebateStage): void;
  addActivity(title: string, detail?: string, tone?: WorkflowActivity["tone"]): void;
  appendHostResearch(chunk: string): void;
  setDebaters(sessionId: string, debaters: DebaterConfig[], debateDeadlineMs: number | null): void;
  setBackgroundImage(path: string): void;
  setAvatarImages(avatars: Record<string, string>): void;
  setSummaryImage(path: string): void;
  setFocusOptions(sessionId: string, focusOptions: FocusOption[]): void;
  setSelectedFocus(selectedFocusId: string): void;
  setIntensityDraft(intensity: "mild" | "balanced" | "intense"): void;
  setUserContextDraft(userContext: string): void;
  appendToken(sessionId: string, speaker: string, turnId: number, token: string, stage?: DebateStage): void;
  finalizeTurn(sessionId: string, speaker: string, turnId: number, fullContent: string, stage?: DebateStage): void;
  appendHostSummary(chunk: string): void;
  markStopRequested(): void;
  setDone(sessionId: string, reportPath: string, summaryImagePath?: string): void;
  setReportMarkdown(text: string): void;
  setError(msg: string): void;
  reset(): void;

  // Follow-up actions
  setFollowUpTarget(target: string | null): void;
  addFollowUpMessage(message: FollowUpMessage): void;
  appendFollowUpToken(followUpId: string, token: string): void;
  finalizeFollowUp(followUpId: string, fullResponse: string): void;
  setFollowUpStreaming(isStreaming: boolean): void;
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
  currentTab: "config" as DebateRoomTab,

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

  // Stage tracking
  currentStage: null as DebateStage | null,
  stageLines: {} as Record<DebateStage, DebateLine[]>,

  images: {
    avatars: {} as Record<string, string>,
  } as DebateImages,

  focusOptions: [] as FocusOption[],
  selectedFocusId: "",
  intensityDraft: "balanced" as const,
  userContextDraft: "",
  isConfigurationReady: false,

  // Follow-up
  followUpMessages: [] as FollowUpMessage[],
  followUpLiveResponse: "",
  followUpTarget: null as string | null,
  isFollowUpStreaming: false,
};

export const useDebateStore = create<DebateState>((set) => ({
  ...initialState,

  // Navigation
  setTab: (tab) => set({ currentTab: tab }),

  start: (topic) =>
    set({
      ...initialState,
      topic,
      currentTab: "host",
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
  setStage: (stage) =>
    set((s) => ({
      currentStage: stage,
      activities: pushActivity(
        s.activities,
        `进入${stage === "opening" ? "开场" : stage === "free_debate" ? "自由辩论" : stage === "closing" ? "总结" : "总结"}阶段`,
        "",
        "live"
      ),
    })),
  addActivity: (title, detail = "", tone = "neutral") =>
    set((s) => ({
      activities: pushActivity(s.activities, title, detail, tone),
    })),
  appendHostResearch: (chunk) =>
    set((s) => ({
      hostResearch: s.hostResearch + chunk,
    })),
  setFocusOptions: (sessionId, focusOptions) =>
    set((s) => ({
      sessionId: s.sessionId || sessionId,
      currentTab: "host",
      focusOptions,
      selectedFocusId: focusOptions[0]?.id || "",
      isConfigurationReady: focusOptions.length > 0,
      activities: pushActivity(
        s.activities,
        "关注切面已生成",
        `主持人已给出 ${focusOptions.length} 个可选讨论切面。`,
        "done",
      ),
    })),
  setSelectedFocus: (selectedFocusId) => set({ selectedFocusId }),
  setIntensityDraft: (intensityDraft) => set({ intensityDraft }),
  setUserContextDraft: (userContextDraft) => set({ userContextDraft }),
  setDebaters: (sessionId, debaters, debateDeadlineMs) =>
    set((s) => ({
      sessionId: s.sessionId || sessionId,
      debateDeadlineMs,
      debaters,
      currentTab: "debate",
      isConfigurationReady: false,
      activities: pushActivity(
        s.activities,
        "辩手阵列已建立",
        `已生成 ${debaters.length} 位立场各异的辩手，倒计时开始。`,
        "done",
      ),
    })),

  setBackgroundImage: (path) =>
    set((s) => ({
      images: { ...s.images, background: path },
      activities: pushActivity(
        s.activities,
        "辩论场景已生成",
        "AI绘制的辩论舞台背景已就绪。",
        "done",
      ),
    })),

  setAvatarImages: (avatars) =>
    set((s) => ({
      images: { ...s.images, avatars: { ...s.images.avatars, ...avatars } },
      debaters: s.debaters.map((d) =>
        avatars[d.name] ? { ...d, avatar_url: avatars[d.name] } : d
      ),
    })),

  setSummaryImage: (path) =>
    set((s) => ({
      images: { ...s.images, summary: path },
      activities: pushActivity(
        s.activities,
        "总结海报已生成",
        "辩论总结可视化海报已就绪。",
        "done",
      ),
    })),
  appendToken: (sessionId, speaker, turnId, token, stage) => {
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
  finalizeTurn: (sessionId, speaker, turnId, fullContent, stage) => {
    const key = `${speaker}-${turnId}`;
    set((s) => {
      const nextBuffers = { ...s.liveBuffers };
      delete nextBuffers[key];
      const newLine: DebateLine = { key, speaker, turnId, content: fullContent, stage };
      const stageKey = stage || "free_debate";
      const currentStageLines = s.stageLines[stageKey] || [];
      return {
        sessionId: s.sessionId || sessionId,
        activeSpeaker: s.activeSpeaker === speaker && s.activeTurnId === turnId ? "" : s.activeSpeaker,
        activeTurnId: s.activeSpeaker === speaker && s.activeTurnId === turnId ? null : s.activeTurnId,
        liveBuffers: nextBuffers,
        lines: [...s.lines, newLine],
        stageLines: {
          ...s.stageLines,
          [stageKey]: [...currentStageLines, newLine],
        },
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
      status: "done" as const,
      phase: "summarizing" as DebatePhase,
      phaseLabel: "正在结束",
      phaseDetail: "已请求提前结束，正在生成总结报告...",
      activities: pushActivity(
        s.activities,
        "已请求提前结束",
        "正在生成总结报告...",
        "neutral",
      ),
    })),
  setDone: (sessionId, reportPath, summaryImagePath) =>
    set((s) => ({
      status: "done",
      phase: "complete",
      phaseLabel: "报告已生成",
      phaseDetail: "主持人总结完成，本轮辩论已归档。",
      currentTab: "summary",
      sessionId,
      reportPath,
      images: summaryImagePath
        ? { ...s.images, summary: summaryImagePath }
        : s.images,
      activeSpeaker: "",
      activeTurnId: null,
      isConfigurationReady: false,
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

  // Follow-up actions
  setFollowUpTarget: (target) => set({ followUpTarget: target }),
  addFollowUpMessage: (message) =>
    set((s) => ({
      followUpMessages: [...s.followUpMessages, message],
      followUpLiveResponse: "",
      activities: pushActivity(
        s.activities,
        `向 ${message.target_role} 提问`,
        message.question.slice(0, 50) + (message.question.length > 50 ? "..." : ""),
        "live"
      ),
    })),
  appendFollowUpToken: (followUpId, token) =>
    set((s) => ({
      followUpLiveResponse: s.followUpLiveResponse + token,
      followUpMessages: s.followUpMessages.map((m) =>
        m.id === followUpId ? { ...m, response: m.response + token } : m
      ),
    })),
  finalizeFollowUp: (followUpId, fullResponse) =>
    set((s) => ({
      followUpLiveResponse: "",
      isFollowUpStreaming: false,
      followUpMessages: s.followUpMessages.map((m) =>
        m.id === followUpId ? { ...m, response: fullResponse, isStreaming: false } : m
      ),
      activities: pushActivity(
        s.activities,
        "跟进问题已回答",
        fullResponse.slice(0, 50) + (fullResponse.length > 50 ? "..." : ""),
        "done"
      ),
    })),
  setFollowUpStreaming: (isStreaming) => set({ isFollowUpStreaming: isStreaming }),
}));
