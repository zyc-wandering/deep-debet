import { EventSourceMessage, fetchEventSource } from "@microsoft/fetch-event-source";
import { useCallback, useMemo, useRef } from "react";
import {
  DebateConfigureRequest,
  DebateConfirmRequest,
  DebatePhase,
  DebateStartRequest,
  DebaterConfig,
  FocusOption,
  StructuredReport,
} from "../types";
import { useDebateStore } from "../store/debateStore";

const DEFAULT_API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").trim();
const LOCAL_FALLBACK_API_BASES = ["http://127.0.0.1:8001", "http://127.0.0.1:8010"];
const OUTDATED_BACKEND_MESSAGE =
  "当前连接的后端还是旧版接口，且没有找到可用的新后端。请重启本地 backend 后再试。";

function resolveImageUrl(apiBase: string, rawPath?: string | null): string | undefined {
  if (!rawPath) return undefined;
  const trimmed = rawPath.trim();
  if (!trimmed) return undefined;
  if (/^(?:https?:)?\/\//i.test(trimmed) || trimmed.startsWith("data:")) return trimmed;
  // Backend returns a relative path like "topic_ts/images/avatar_name.png"
  // Encode each segment separately to preserve directory structure
  const normalized = trimmed.replace(/\\/g, "/");
  const segments = normalized.split("/").filter(Boolean);
  if (!segments.length) return undefined;
  const encoded = segments.map((s) => encodeURIComponent(s)).join("/");
  return `${apiBase}/api/images/${encoded}`;
}

interface PhasePayload {
  session_id?: string;
  phase: DebatePhase;
  title: string;
  detail?: string;
}

type TraceAwarePayload = {
  session_id?: string;
  [key: string]: unknown;
};

export function useDebate() {
  const abortRef = useRef<AbortController | null>(null);
  const apiBaseRef = useRef(DEFAULT_API_BASE);
  const phase3SupportRef = useRef<boolean | null>(null);

  const fetchReport = useCallback(async (reportPath: string) => {
    if (!reportPath.trim()) return;
    const url = `${apiBaseRef.current}/api/debate/report?path=${encodeURIComponent(reportPath)}`;
    const resp = await fetch(url);
    if (!resp.ok) return;
    const text = await resp.text();
    useDebateStore.getState().setReportMarkdown(text);
  }, []);

  const ensurePhase3Backend = useCallback(async () => {
    if (phase3SupportRef.current === true) return;

    const candidates = [DEFAULT_API_BASE, ...LOCAL_FALLBACK_API_BASES].filter(
      (base, index, list) => Boolean(base) && list.indexOf(base) === index,
    );

    for (const base of candidates) {
      try {
        const response = await fetch(`${base}/openapi.json`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) continue;

        const schema = (await response.json()) as {
          paths?: Record<string, unknown>;
          components?: {
            schemas?: Record<string, { properties?: Record<string, unknown> }>;
          };
        };

        const hasConfigureEndpoint = Boolean(schema.paths?.["/api/debate/configure"]);
        const hasConfirmEndpoint = Boolean(schema.paths?.["/api/debate/confirm"]);
        const startProps = schema.components?.schemas?.DebateStartRequest?.properties || {};
        const stillUsesLegacyStartConfig = "pre_debate_config" in startProps;

        if (hasConfigureEndpoint && hasConfirmEndpoint && !stillUsesLegacyStartConfig) {
          apiBaseRef.current = base;
          phase3SupportRef.current = true;
          return;
        }
      } catch {
        continue;
      }
    }

    phase3SupportRef.current = false;
    throw new Error(OUTDATED_BACKEND_MESSAGE);
  }, []);

  const handleMessage = useCallback(
    async (msg: EventSourceMessage) => {
      if (!msg.event) return;
      const data = (msg.data ? (JSON.parse(msg.data) as TraceAwarePayload) : {}) as TraceAwarePayload;

      if (msg.event === "phase") {
        const phaseData = data as unknown as PhasePayload;
        if (phaseData.session_id) {
          useDebateStore.getState().setSessionId(phaseData.session_id);
        }
        useDebateStore.getState().setBackendPhase(phaseData.phase, phaseData.title, phaseData.detail || "");
        return;
      }

      if (msg.event === "host_research") {
        const researchData = data as { chunk: string; session_id: string };
        useDebateStore.getState().appendHostResearch(researchData.chunk);
        if (researchData.session_id) {
          useDebateStore.getState().setSessionId(researchData.session_id);
        }
        return;
      }

      if (msg.event === "focus_options_ready") {
        const focusData = data as { session_id: string; focus_options: FocusOption[] };
        useDebateStore.getState().setFocusOptions(focusData.session_id, focusData.focus_options);
        return;
      }

      if (msg.event === "debaters_ready") {
        const debaterData = data as {
          session_id: string;
          debaters: DebaterConfig[];
          deadline_at?: string | null;
          main_count?: number;
        };
        const debaters = debaterData.debaters.map((debater) => ({
          ...debater,
          avatar_url: resolveImageUrl(apiBaseRef.current, debater.avatar_url) || debater.avatar_url,
        }));
        useDebateStore.getState().setDebaters(
          debaterData.session_id,
          debaters,
          debaterData.deadline_at ? Date.parse(debaterData.deadline_at) : null,
          debaterData.main_count,
        );
        return;
      }

      // background_ready - ignore (removed feature)
      if (msg.event === "background_ready") {
        return;
      }

      if (msg.event === "avatars_ready") {
        const avatarData = data as { avatars: Record<string, string> };
        const avatars: Record<string, string> = {};
        Object.entries(avatarData.avatars).forEach(([name, path]) => {
          const imageUrl = resolveImageUrl(apiBaseRef.current, path as string);
          if (imageUrl) {
            avatars[name] = imageUrl;
          }
        });
        useDebateStore.getState().setAvatarImages(avatars);
        return;
      }

      if (msg.event === "debate_token") {
        const tokenData = data as {
          session_id: string;
          speaker: string;
          turn_id: number;
          token: string;
          stage?: "opening" | "free_debate" | "closing" | "summary";
        };
        useDebateStore.getState().appendToken(
          tokenData.session_id,
          tokenData.speaker,
          tokenData.turn_id,
          tokenData.token,
          tokenData.stage,
        );
        return;
      }

      if (msg.event === "debate_turn_start") {
        const turnStartData = data as {
          session_id: string;
          speaker: string;
          turn_id: number;
          stage?: "opening" | "free_debate" | "closing" | "summary";
        };
        useDebateStore.getState().setPreparingTurn(
          turnStartData.session_id,
          turnStartData.speaker,
          turnStartData.turn_id,
          turnStartData.stage,
        );
        return;
      }

      if (msg.event === "stage_change") {
        const stageData = data as { stage: "opening" | "free_debate" | "closing" | "summary" };
        useDebateStore.getState().setStage(stageData.stage);
        return;
      }

      if (msg.event === "debate_turn_end") {
        const turnEndData = data as {
          session_id: string;
          speaker: string;
          turn_id: number;
          full_content: string;
          stage?: "opening" | "free_debate" | "closing" | "summary";
        };
        useDebateStore.getState().finalizeTurn(
          turnEndData.session_id,
          turnEndData.speaker,
          turnEndData.turn_id,
          turnEndData.full_content,
          turnEndData.stage,
        );
        return;
      }

      if (msg.event === "host_summary") {
        const summaryData = data as { chunk: string };
        useDebateStore.getState().appendHostSummary(summaryData.chunk);
        return;
      }

      if (msg.event === "structured_report") {
        const reportData = data as { report: StructuredReport };
        useDebateStore.getState().setStructuredReport(reportData.report);
        return;
      }

      if (msg.event === "done") {
        const doneData = data as { session_id: string; report_path: string };
        useDebateStore.getState().setDone(doneData.session_id, doneData.report_path);
        await fetchReport(doneData.report_path);
        abortRef.current?.abort();
        abortRef.current = null;
        return;
      }

      if (msg.event === "error") {
        const errorData = data as { message: string };
        useDebateStore.getState().setError(errorData.message || "Unknown error");
        abortRef.current = null;
      }
    },
    [fetchReport],
  );

  const runStream = useCallback(
    async (url: string, body: string) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        await fetchEventSource(url, {
          method: "POST",
          openWhenHidden: true,
          signal: ctrl.signal,
          headers: { "Content-Type": "application/json" },
          body,
          onopen: async (response) => {
            if (!response.ok) {
              const errorMsg = `Failed to connect: ${response.status}`;
              useDebateStore.getState().setError(errorMsg);
              throw new Error(errorMsg);
            }
          },
          onmessage: handleMessage,
          onclose: () => {
            return;
          },
          onerror: (error) => {
            if (!ctrl.signal.aborted) {
              const errorMsg = error.message || "Connection error";
              useDebateStore.getState().setError(errorMsg);
            }
            // Always throw to prevent fetchEventSource from auto-retrying.
            // Our SSE streams are one-shot (start, configure, confirm) — never reconnect.
            throw error;
          },
        });
      } catch (error) {
        if (ctrl.signal.aborted) return;
        // "SSE stream closed" is our intentional close — not a real error
        if (error instanceof Error && error.message === "SSE stream closed") return;
        const message = error instanceof Error ? error.message : "Connection error";
        useDebateStore.getState().setError(message);
      }
    },
    [handleMessage],
  );

  const api = useMemo(
    () => ({
      start: async (payload: DebateStartRequest) => {
        try {
          await ensurePhase3Backend();
        } catch (error) {
          const message = error instanceof Error ? error.message : OUTDATED_BACKEND_MESSAGE;
          useDebateStore.getState().setError(message);
          return;
        }

        useDebateStore.getState().start(payload.topic, payload.debate_language);
        await runStream(`${apiBaseRef.current}/api/debate/start`, JSON.stringify(payload));
      },
      configure: async (payload: DebateConfigureRequest) => {
        await runStream(`${apiBaseRef.current}/api/debate/configure`, JSON.stringify(payload));
      },
      confirm: async (payload: DebateConfirmRequest) => {
        await runStream(`${apiBaseRef.current}/api/debate/confirm`, JSON.stringify(payload));
      },
      stop: async () => {
        const store = useDebateStore.getState();
        const sessionId = store.sessionId;
        if (!sessionId) return;

        store.markStopRequested();

        try {
          await fetch(`${apiBaseRef.current}/api/debate/stop`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId }),
          });
        } catch (error) {
          const message = error instanceof Error ? error.message : "Stop request failed";
          useDebateStore.getState().setError(message);
        }
      },
      fetchReport,
      getApiBase: () => apiBaseRef.current,
    }),
    [ensurePhase3Backend, fetchReport, runStream],
  );

  return api;
}
