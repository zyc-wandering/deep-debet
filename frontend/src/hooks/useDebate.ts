import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useCallback, useMemo, useRef } from "react";
import {
  DebateConfigureRequest,
  DebatePhase,
  DebateStartRequest,
  DebaterConfig,
  FocusOption,
  StructuredReport,
  TraceEntry,
  TraceMeta,
} from "../types";
import { useDebateStore } from "../store/debateStore";

const DEFAULT_API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").trim();
const LOCAL_FALLBACK_API_BASES = ["http://127.0.0.1:8001", "http://127.0.0.1:8010"];
const OUTDATED_BACKEND_MESSAGE =
  "当前连接的后端还是旧版接口，且没有找到可用的 Phase 3 新后端。请重启本地 backend 后再试。";

function resolveImageUrl(apiBase: string, rawPath?: string | null): string | undefined {
  if (!rawPath) return undefined;

  const trimmed = rawPath.trim();
  if (!trimmed) return undefined;

  if (/^(?:https?:)?\/\//i.test(trimmed) || trimmed.startsWith("data:")) {
    return trimmed;
  }

  const normalized = trimmed.replace(/\\/g, "/");
  const filename = normalized.split("/").filter(Boolean).pop();
  if (!filename) return undefined;

  return `${apiBase}/api/images/${encodeURIComponent(filename)}`;
}

interface PhasePayload {
  session_id?: string;
  phase: DebatePhase;
  title: string;
  detail?: string;
}

type TraceAwarePayload = {
  session_id?: string;
  _trace?: TraceMeta;
  [key: string]: unknown;
};

function summarizeTraceEvent(event: string, data: TraceAwarePayload): string {
  if (event === "phase") {
    return typeof data.title === "string" ? data.title : "Phase update";
  }
  if (event === "debate_turn_start") {
    return `${String(data.speaker || "Speaker")} turn ${Number(data.turn_id ?? 0) + 1} started`;
  }
  if (event === "debate_turn_end") {
    return `${String(data.speaker || "Speaker")} turn ${Number(data.turn_id ?? 0) + 1} completed`;
  }
  if (event === "done") {
    return "Debate run completed";
  }
  if (event === "error") {
    return typeof data.message === "string" ? data.message : "Run failed";
  }
  return event.replaceAll("_", " ");
}

function buildTraceEntry(event: string, data: TraceAwarePayload, trace: TraceMeta): TraceEntry {
  return {
    id: `${trace.trace_id}-${trace.event_seq}`,
    event,
    session_id: typeof data.session_id === "string" ? data.session_id : undefined,
    trace,
    summary: summarizeTraceEvent(event, data),
  };
}

export function useDebate() {
  const abortRef = useRef<AbortController | null>(null);
  const apiBaseRef = useRef(DEFAULT_API_BASE);
  const phase3SupportRef = useRef<boolean | null>(null);

  const fetchReport = useCallback(async (reportPath: string) => {
    if (!reportPath.trim()) {
      return;
    }
    const url = `${apiBaseRef.current}/api/debate/report?path=${encodeURIComponent(reportPath)}`;
    const resp = await fetch(url);
    if (!resp.ok) return;
    const text = await resp.text();
    useDebateStore.getState().setReportMarkdown(text);
  }, []);

  const ensurePhase3Backend = useCallback(async () => {
    if (phase3SupportRef.current === true) {
      return;
    }

    const candidates = [DEFAULT_API_BASE, ...LOCAL_FALLBACK_API_BASES].filter(
      (base, index, list) => Boolean(base) && list.indexOf(base) === index,
    );

    for (const base of candidates) {
      try {
        const response = await fetch(`${base}/openapi.json`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          continue;
        }

        const schema = (await response.json()) as {
          paths?: Record<string, unknown>;
          components?: {
            schemas?: Record<
              string,
              {
                properties?: Record<string, unknown>;
              }
            >;
          };
        };

        const hasConfigureEndpoint = Boolean(schema.paths?.["/api/debate/configure"]);
        const startProps = schema.components?.schemas?.DebateStartRequest?.properties || {};
        const stillUsesLegacyStartConfig = "pre_debate_config" in startProps;

        if (hasConfigureEndpoint && !stillUsesLegacyStartConfig) {
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
    async (msg: MessageEvent) => {
      if (!msg.event) return;
      const data = (msg.data ? (JSON.parse(msg.data) as TraceAwarePayload) : {}) as TraceAwarePayload;
      const trace = data._trace;

      if (trace) {
        useDebateStore.getState().addTraceEntry(buildTraceEntry(msg.event, data, trace));
        if (typeof data.session_id === "string") {
          useDebateStore.getState().setSessionId(data.session_id);
        }
        if (typeof trace.journal_path === "string" && trace.journal_path) {
          useDebateStore.getState().setTraceJournalPath(trace.journal_path);
        }
      }

      if (msg.event === "phase") {
        const phaseData = data as PhasePayload;
        if (phaseData.session_id) {
          useDebateStore.getState().setSessionId(phaseData.session_id);
        }
        useDebateStore.getState().setPhase(phaseData.phase, phaseData.title, phaseData.detail || "");
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
        const focusData = data as {
          session_id: string;
          focus_options: FocusOption[];
        };
        useDebateStore.getState().setFocusOptions(focusData.session_id, focusData.focus_options);
        return;
      }

      if (msg.event === "debaters_ready") {
        const debaterData = data as {
          session_id: string;
          debaters: DebaterConfig[];
          deadline_at?: string | null;
        };
        useDebateStore.getState().setDebaters(
          debaterData.session_id,
          debaterData.debaters,
          debaterData.deadline_at ? Date.parse(debaterData.deadline_at) : null,
        );
        return;
      }

      if (msg.event === "background_ready") {
        const bgData = data as { background_path: string };
        const imageUrl = resolveImageUrl(apiBaseRef.current, bgData.background_path);
        if (imageUrl) {
          useDebateStore.getState().setBackgroundImage(imageUrl);
        }
        return;
      }

      if (msg.event === "avatars_ready") {
        const avatarData = data as { avatars: Record<string, string> };
        const avatars: Record<string, string> = {};
        Object.entries(avatarData.avatars).forEach(([name, path]) => {
          const imageUrl = resolveImageUrl(apiBaseRef.current, path);
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
        const stageData = data as {
          stage: "opening" | "free_debate" | "closing" | "summary";
        };
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
        const doneData = data as {
          session_id: string;
          report_path: string;
          summary_image_path?: string;
          trace_journal_path?: string;
        };
        const summaryImageUrl = resolveImageUrl(apiBaseRef.current, doneData.summary_image_path);
        useDebateStore.getState().setDone(doneData.session_id, doneData.report_path, summaryImageUrl);
        if (doneData.trace_journal_path) {
          useDebateStore.getState().setTraceJournalPath(doneData.trace_journal_path);
        }
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
          onerror: (error) => {
            if (ctrl.signal.aborted) {
              return;
            }
            const errorMsg = error.message || "Connection error";
            useDebateStore.getState().setError(errorMsg);
          },
        });
      } catch (error) {
        if (ctrl.signal.aborted) {
          return;
        }
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
    }),
    [ensurePhase3Backend, fetchReport, runStream],
  );

  return api;
}
