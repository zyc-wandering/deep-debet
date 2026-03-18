import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  Phase,
  DebateLine,
  DebateLanguage,
  DebaterConfig,
  DebatePhase,
  DebateStage,
  FollowUpMessage,
  FocusOption,
  PreparingTurn,
  StructuredReport,
  TranscriptMessage,
  WorkflowActivity,
} from "../types";

type RunStatus = "idle" | "running" | "done" | "error";

interface DebateState {
  phase: Phase;
  backendPhase: DebatePhase;
  phaseLabel: string;
  phaseDetail: string;
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
  liveBuffers: Record<string, { content: string; stage?: DebateStage }>;
  activeSpeaker: string;
  activeTurnId: number | null;
  preparingTurn: PreparingTurn | null;
  currentStage: DebateStage | null;
  stageLines: Record<string, DebateLine[]>;
  transcript: TranscriptMessage[];

  reportPath: string;
  reportMarkdown: string;
  structuredReport: StructuredReport | null;

  errorMessage: string;
  activities: WorkflowActivity[];

  followUpMessages: FollowUpMessage[];
  followUpLiveResponse: string;
  followUpTarget: string | null;
  isFollowUpStreaming: boolean;

  setPhase(phase: Phase): void;
  start(topic: string, debateLanguage: DebateLanguage): void;
  setSessionId(sessionId: string): void;
  setBackendPhase(phase: DebatePhase, label: string, detail?: string): void;
  setStage(stage: DebateStage): void;
  addActivity(title: string, detail?: string, tone?: WorkflowActivity["tone"]): void;
  appendHostResearch(chunk: string): void;
  setFocusOptions(sessionId: string, focusOptions: FocusOption[]): void;
  setSelectedFocus(selectedFocusId: string): void;
  setIntensityDraft(intensity: "mild" | "balanced" | "intense"): void;
  setUserContextDraft(userContext: string): void;
  setDebaters(sessionId: string, debaters: DebaterConfig[], debateDeadlineMs: number | null, mainCount?: number): void;
  setPreparingTurn(sessionId: string, speaker: string, turnId: number, stage?: DebateStage): void;
  appendToken(sessionId: string, speaker: string, turnId: number, token: string, stage?: DebateStage): void;
  finalizeTurn(sessionId: string, speaker: string, turnId: number, fullContent: string, stage?: DebateStage): void;
  appendHostSummary(chunk: string): void;
  markStopRequested(): void;
  setDone(sessionId: string, reportPath: string): void;
  setReportMarkdown(text: string): void;
  setStructuredReport(report: StructuredReport): void;
  setError(msg: string): void;
  reset(): void;
  setAvatarImages(avatars: Record<string, string>): void;
  swapDebater(selectedIndex: number, subIndex: number): void;
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

const ephemeralState = {
  backendPhase: "idle" as DebatePhase,
  phaseLabel: "",
  phaseDetail: "",
  liveBuffers: {} as Record<string, { content: string; stage?: DebateStage }>,
  activeSpeaker: "",
  activeTurnId: null as number | null,
  preparingTurn: null as PreparingTurn | null,
  stageLines: {} as Record<string, DebateLine[]>,
  errorMessage: "",
  activities: [] as WorkflowActivity[],
  followUpLiveResponse: "",
  followUpTarget: null as string | null,
  isFollowUpStreaming: false,
};

const persistedState = {
  phase: "config" as Phase,
  status: "idle" as RunStatus,
  topic: "",
  debateLanguage: "zh" as DebateLanguage,
  sessionId: "",
  debateDeadlineMs: null as number | null,
  hostResearch: "",
  focusOptions: [] as FocusOption[],
  selectedFocusId: "",
  intensityDraft: "balanced" as const,
  userContextDraft: "",
  isConfigurationReady: false,
  debaters: [] as DebaterConfig[],
  substituteDebaters: [] as DebaterConfig[],
  hostSummary: "",
  lines: [] as DebateLine[],
  currentStage: null as DebateStage | null,
  transcript: [] as TranscriptMessage[],
  reportPath: "",
  reportMarkdown: "",
  structuredReport: null as StructuredReport | null,
  followUpMessages: [] as FollowUpMessage[],
};

export const useDebateStore = create<DebateState>()(
  persist(
    (set, get) => ({
      ...ephemeralState,
      ...persistedState,

      setPhase: (phase) => set({ phase }),

      start: (topic, debateLanguage) =>
        set({
          ...ephemeralState,
          ...persistedState,
          topic,
          debateLanguage,
          phase: "research",
          status: "running",
          backendPhase: "booting",
          phaseLabel: "辩题已提交",
          phaseDetail: "正在建立会话并准备主持人工作流。",
          activities: [
            makeActivity("已提交新辩题", "系统已接收参数，准备开始主持人调研。", "live"),
          ],
        }),

      setSessionId: (sessionId) =>
        set((s) => ({ sessionId: s.sessionId || sessionId })),

      setBackendPhase: (backendPhase, label, detail = "") =>
        set((s) => ({
          backendPhase,
          phaseLabel: label,
          phaseDetail: detail,
          activities: pushActivity(s.activities, label, detail, backendPhase === "error" ? "error" : "live"),
        })),

      setStage: (stage) =>
        set((s) => ({
          currentStage: stage,
          activities: pushActivity(
            s.activities,
            `进入${stage === "opening" ? "开场" : stage === "free_debate" ? "自由辩论" : stage === "closing" ? "总结陈词" : "总结"}阶段`,
            "",
            "live",
          ),
        })),

      addActivity: (title, detail = "", tone = "neutral") =>
        set((s) => ({ activities: pushActivity(s.activities, title, detail, tone) })),

      appendHostResearch: (chunk) =>
        set((s) => ({ hostResearch: s.hostResearch + chunk })),

      setFocusOptions: (sessionId, focusOptions) =>
        set((s) => ({
          sessionId: s.sessionId || sessionId,
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

      setDebaters: (sessionId, debaters, debateDeadlineMs, mainCount) =>
        set((s) => {
          const mc = mainCount ?? debaters.length;
          const selected = debaters.slice(0, mc);
          const subs = debaters.slice(mc);
          return {
            sessionId: s.sessionId || sessionId,
            debateDeadlineMs,
            debaters: selected,
            substituteDebaters: subs,
            phase: "drafting",
            isConfigurationReady: false,
            activities: pushActivity(
              s.activities,
              "辩手阵列已建立",
              `已生成 ${selected.length} 位主力 + ${subs.length} 位替补辩手。`,
              "done",
            ),
          };
        }),

      setAvatarImages: (avatars) =>
        set((s) => ({
          debaters: s.debaters.map((d) =>
            avatars[d.name] ? { ...d, avatar_url: avatars[d.name] } : d,
          ),
          substituteDebaters: s.substituteDebaters.map((d) =>
            avatars[d.name] ? { ...d, avatar_url: avatars[d.name] } : d,
          ),
        })),

      swapDebater: (selectedIndex, subIndex) =>
        set((s) => {
          const newSelected = [...s.debaters];
          const newSubs = [...s.substituteDebaters];
          const temp = newSelected[selectedIndex];
          newSelected[selectedIndex] = newSubs[subIndex];
          newSubs[subIndex] = temp;
          return { debaters: newSelected, substituteDebaters: newSubs };
        }),

      setPreparingTurn: (sessionId, speaker, turnId, stage) =>
        set((s) => ({
          sessionId: s.sessionId || sessionId,
          phase: "arena",
          activeSpeaker: speaker,
          activeTurnId: turnId,
          preparingTurn: { speaker, turnId, stage },
          activities: pushActivity(
            s.activities,
            `${speaker} 正在准备发言`,
            `第 ${turnId + 1} 轮即将开始。`,
            "live",
          ),
        })),

      appendToken: (sessionId, speaker, turnId, token, stage) => {
        const key = `${speaker}-${turnId}`;
        const s = get();
        const firstTokenOfTurn = !s.liveBuffers[key];
        const preparingTurnMatches =
          s.preparingTurn?.speaker === speaker && s.preparingTurn?.turnId === turnId;
        set({
          sessionId: s.sessionId || sessionId,
          phase: "arena",
          activeSpeaker: speaker,
          activeTurnId: turnId,
          preparingTurn: preparingTurnMatches ? null : s.preparingTurn,
          liveBuffers: {
            ...s.liveBuffers,
            [key]: {
              content: (s.liveBuffers[key]?.content || "") + token,
              stage: stage || s.liveBuffers[key]?.stage,
            },
          },
          activities: firstTokenOfTurn
            ? pushActivity(s.activities, `${speaker} 开始发言`, `第 ${turnId + 1} 轮正在生成中。`, "live")
            : s.activities,
        });
      },

      finalizeTurn: (sessionId, speaker, turnId, fullContent, stage) => {
        const key = `${speaker}-${turnId}`;
        const s = get();
        const nextBuffers = { ...s.liveBuffers };
        delete nextBuffers[key];
        const newLine: DebateLine = { key, speaker, turnId, content: fullContent, stage };
        const stageKey = stage || "free_debate";
        const msg: TranscriptMessage = {
          id: key,
          timestamp: new Date(),
          speaker,
          content: fullContent,
          stage: (stage || "free_debate") as TranscriptMessage["stage"],
          turnId,
        };
        set({
          sessionId: s.sessionId || sessionId,
          activeSpeaker: s.activeSpeaker === speaker && s.activeTurnId === turnId ? "" : s.activeSpeaker,
          activeTurnId: s.activeSpeaker === speaker && s.activeTurnId === turnId ? null : s.activeTurnId,
          preparingTurn:
            s.preparingTurn?.speaker === speaker && s.preparingTurn?.turnId === turnId ? null : s.preparingTurn,
          liveBuffers: nextBuffers,
          lines: [...s.lines, newLine],
          stageLines: { ...s.stageLines, [stageKey]: [...(s.stageLines[stageKey] || []), newLine] },
          transcript: [...s.transcript, msg],
          activities: pushActivity(s.activities, `${speaker} 完成发言`, `第 ${turnId + 1} 轮已写入记录。`, "done"),
        });
      },

      appendHostSummary: (chunk) =>
        set((s) => ({ hostSummary: s.hostSummary + chunk, phase: "summary" })),

      markStopRequested: () =>
        set((s) => ({
          activities: pushActivity(
            s.activities,
            "已请求提前结束",
            "系统会在当前轮次结束后进入主持人总结。",
            "neutral",
          ),
        })),

      setDone: (sessionId, reportPath) =>
        set((s) => ({
          status: "done",
          backendPhase: "complete",
          phaseLabel: "报告已生成",
          phaseDetail: "主持人总结完成，本轮辩论已归档。",
          phase: "summary",
          sessionId,
          reportPath,
          activeSpeaker: "",
          activeTurnId: null,
          preparingTurn: null,
          isConfigurationReady: false,
          activities: pushActivity(
            s.activities,
            "本轮辩论已完成",
            "可继续阅读报告，或发起下一轮辩论。",
            "done",
          ),
        })),

      setReportMarkdown: (text) => set({ reportMarkdown: text }),
      setStructuredReport: (report) => set({ structuredReport: report }),

      setError: (msg) =>
        set((s) => ({
          status: "error",
          backendPhase: "error",
          phaseLabel: "流程异常",
          phaseDetail: msg,
          errorMessage: msg,
          preparingTurn: null,
          activities: pushActivity(s.activities, "发生错误", msg, "error"),
        })),

      reset: () =>
        set({ ...ephemeralState, ...persistedState }),

      setFollowUpTarget: (target) => set({ followUpTarget: target }),

      addFollowUpMessage: (message) =>
        set((s) => ({
          followUpMessages: [...s.followUpMessages, message],
          followUpLiveResponse: "",
          activities: pushActivity(
            s.activities,
            `向 ${message.target_role} 提问`,
            message.question.slice(0, 50) + (message.question.length > 50 ? "..." : ""),
            "live",
          ),
        })),

      appendFollowUpToken: (followUpId, token) =>
        set((s) => ({
          followUpLiveResponse: s.followUpLiveResponse + token,
          followUpMessages: s.followUpMessages.map((m) =>
            m.id === followUpId ? { ...m, response: m.response + token } : m,
          ),
        })),

      finalizeFollowUp: (followUpId, fullResponse) =>
        set((s) => ({
          followUpLiveResponse: "",
          isFollowUpStreaming: false,
          followUpMessages: s.followUpMessages.map((m) =>
            m.id === followUpId ? { ...m, response: fullResponse, isStreaming: false } : m,
          ),
          activities: pushActivity(
            s.activities,
            "跟进问题已回答",
            fullResponse.slice(0, 50) + (fullResponse.length > 50 ? "..." : ""),
            "done",
          ),
        })),

      setFollowUpStreaming: (isStreaming) => set({ isFollowUpStreaming: isStreaming }),
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
