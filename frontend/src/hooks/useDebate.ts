import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useCallback, useMemo, useRef } from "react";
import { DebateConfigureRequest, DebatePhase, DebateStartRequest, DebaterConfig, FocusOption } from "../types";
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

export function useDebate() {
  const abortRef = useRef<AbortController | null>(null);
  const apiBaseRef = useRef(DEFAULT_API_BASE);
  const phase3SupportRef = useRef<boolean | null>(null);

  const fetchReport = useCallback(async (reportPath: string) => {
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

      if (msg.event === "phase") {
        const data = JSON.parse(msg.data) as PhasePayload;
        if (data.session_id) {
          useDebateStore.getState().setSessionId(data.session_id);
        }
        useDebateStore.getState().setPhase(data.phase, data.title, data.detail || "");
        return;
      }

      if (msg.event === "host_research") {
        const data = JSON.parse(msg.data) as { chunk: string; session_id: string };
        useDebateStore.getState().appendHostResearch(data.chunk);
        if (data.session_id) {
          useDebateStore.getState().setSessionId(data.session_id);
        }
        return;
      }

      if (msg.event === "focus_options_ready") {
        const data = JSON.parse(msg.data) as {
          session_id: string;
          focus_options: FocusOption[];
        };
        useDebateStore.getState().setFocusOptions(data.session_id, data.focus_options);
        return;
      }

      if (msg.event === "debaters_ready") {
        const data = JSON.parse(msg.data) as {
          session_id: string;
          debaters: DebaterConfig[];
          deadline_at?: string | null;
        };
        useDebateStore.getState().setDebaters(
          data.session_id,
          data.debaters,
          data.deadline_at ? Date.parse(data.deadline_at) : null,
        );
        return;
      }

      if (msg.event === "background_ready") {
        const data = JSON.parse(msg.data) as { background_path: string };
        const imageUrl = resolveImageUrl(apiBaseRef.current, data.background_path);
        if (imageUrl) {
          useDebateStore.getState().setBackgroundImage(imageUrl);
        }
        return;
      }

      if (msg.event === "avatars_ready") {
        const data = JSON.parse(msg.data) as { avatars: Record<string, string> };
        const avatars: Record<string, string> = {};
        Object.entries(data.avatars).forEach(([name, path]) => {
          const imageUrl = resolveImageUrl(apiBaseRef.current, path);
          if (imageUrl) {
            avatars[name] = imageUrl;
          }
        });
        useDebateStore.getState().setAvatarImages(avatars);
        return;
      }

      if (msg.event === "debate_token") {
        const data = JSON.parse(msg.data) as {
          session_id: string;
          speaker: string;
          turn_id: number;
          token: string;
          stage?: "opening" | "free_debate" | "closing" | "summary";
        };
        useDebateStore.getState().appendToken(
          data.session_id,
          data.speaker,
          data.turn_id,
          data.token,
          data.stage,
        );
        return;
      }

      if (msg.event === "stage_change") {
        const data = JSON.parse(msg.data) as {
          stage: "opening" | "free_debate" | "closing" | "summary";
        };
        useDebateStore.getState().setStage(data.stage);
        return;
      }

      if (msg.event === "debate_turn_end") {
        const data = JSON.parse(msg.data) as {
          session_id: string;
          speaker: string;
          turn_id: number;
          full_content: string;
          stage?: "opening" | "free_debate" | "closing" | "summary";
        };
        useDebateStore.getState().finalizeTurn(
          data.session_id,
          data.speaker,
          data.turn_id,
          data.full_content,
          data.stage,
        );
        return;
      }

      if (msg.event === "host_summary") {
        const data = JSON.parse(msg.data) as { chunk: string };
        useDebateStore.getState().appendHostSummary(data.chunk);
        return;
      }

      if (msg.event === "done") {
        const data = JSON.parse(msg.data) as {
          session_id: string;
          report_path: string;
          summary_image_path?: string;
        };
        const summaryImageUrl = resolveImageUrl(apiBaseRef.current, data.summary_image_path);
        useDebateStore.getState().setDone(data.session_id, data.report_path, summaryImageUrl);
        await fetchReport(data.report_path);
        abortRef.current?.abort();
        abortRef.current = null;
        return;
      }

      if (msg.event === "error") {
        const data = JSON.parse(msg.data) as { message: string };
        useDebateStore.getState().setError(data.message || "Unknown error");
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

        useDebateStore.getState().start(payload.topic);
        await runStream(`${apiBaseRef.current}/api/debate/start`, JSON.stringify(payload));
      },
      configure: async (payload: DebateConfigureRequest) => {
        await runStream(`${apiBaseRef.current}/api/debate/configure`, JSON.stringify(payload));
      },
      stop: async () => {
        const store = useDebateStore.getState();
        const sessionId = store.sessionId;
        if (!sessionId) return;

        abortRef.current?.abort();
        abortRef.current = null;

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
