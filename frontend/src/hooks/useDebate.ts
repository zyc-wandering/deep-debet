import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useCallback, useMemo, useRef } from "react";
import { DebatePhase, DebateStartRequest, DebaterConfig } from "../types";
import { useDebateStore } from "../store/debateStore";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").trim();

interface PhasePayload {
  session_id?: string;
  phase: DebatePhase;
  title: string;
  detail?: string;
}

export function useDebate() {
  const abortRef = useRef<AbortController | null>(null);

  const fetchReport = useCallback(async (reportPath: string) => {
    const url = `${API_BASE}/api/debate/report?path=${encodeURIComponent(reportPath)}`;
    const resp = await fetch(url);
    if (!resp.ok) return;
    const text = await resp.text();
    useDebateStore.getState().setReportMarkdown(text);
  }, []);

  const api = useMemo(
    () => ({
      start: async (payload: DebateStartRequest) => {
        console.log("[Debate] Starting debate with payload:", payload);
        abortRef.current?.abort();
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        useDebateStore.getState().start(payload.topic);
        console.log("[Debate] Store initialized, connecting to SSE...");

        const url = `${API_BASE}/api/debate/start`;
        const body = JSON.stringify(payload);
        console.log("[Debate] Sending request to:", url);
        console.log("[Debate] Request body:", body);

        try {
          await fetchEventSource(url, {
            method: "POST",
            openWhenHidden: true,
            signal: ctrl.signal,
            headers: { "Content-Type": "application/json" },
            body: body,
            onopen: async (response) => {
              console.log("[SSE] Connection opened, status:", response.status);
              if (!response.ok) {
                const errorMsg = `Failed to connect: ${response.status}`;
                console.error("[SSE] Connection failed:", errorMsg);
                useDebateStore.getState().setError(errorMsg);
                throw new Error(errorMsg);
              }
            },
            onmessage: async (msg) => {
              console.log("[SSE] Message received:", msg.event, msg.data);
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

              if (msg.event === "debaters_ready") {
                const data = JSON.parse(msg.data) as {
                  session_id: string;
                  debaters: DebaterConfig[];
                  deadline_at?: string;
                };
                useDebateStore.getState().setDebaters(
                  data.session_id,
                  data.debaters,
                  data.deadline_at ? Date.parse(data.deadline_at) : null,
                );
                return;
              }

              if (msg.event === "background_ready") {
                const data = JSON.parse(msg.data) as {
                  session_id: string;
                  background_path: string;
                };
                // Convert local path to API URL
                const filename = data.background_path.split("/").pop() || data.background_path.split("\\").pop();
                useDebateStore.getState().setBackgroundImage(`/api/images/${filename}`);
                return;
              }

              if (msg.event === "avatars_ready") {
                const data = JSON.parse(msg.data) as {
                  session_id: string;
                  avatars: Record<string, string>;
                };
                // Convert local paths to API URLs
                const avatars: Record<string, string> = {};
                Object.entries(data.avatars).forEach(([name, path]) => {
                  const filename = path.split("/").pop() || path.split("\\").pop();
                  avatars[name] = `/api/images/${filename}`;
                });
                useDebateStore.getState().setAvatarImages(avatars);
                // Auto-switch to debate tab when ready
                useDebateStore.getState().setTab("debate");
                return;
              }

              if (msg.event === "debate_token") {
                const data = JSON.parse(msg.data) as {
                  session_id: string;
                  speaker: string;
                  turn_id: number;
                  token: string;
                };
                useDebateStore.getState().appendToken(data.session_id, data.speaker, data.turn_id, data.token);
                return;
              }

              if (msg.event === "stage_change") {
                const data = JSON.parse(msg.data) as {
                  session_id: string;
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
                // Convert local path to API URL if exists
                let summaryImageUrl: string | undefined;
                if (data.summary_image_path) {
                  const filename = data.summary_image_path.split("/").pop() || data.summary_image_path.split("\\").pop();
                  summaryImageUrl = `/api/images/${filename}`;
                }
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
            onerror: (error) => {
              console.error("[SSE] Connection error:", error);
              if (ctrl.signal.aborted) {
                console.log("[SSE] Connection aborted by user");
                return;
              }
              const errorMsg = error.message || "Connection error";
              useDebateStore.getState().setError(errorMsg);
              // Don't throw here - let the library handle reconnection
            },
          });
        } catch (error) {
          console.error("[SSE] Fatal error:", error);
          if (ctrl.signal.aborted) {
            console.log("[SSE] Request aborted, not showing error");
            return;
          }
          const message = error instanceof Error ? error.message : "Connection error";
          useDebateStore.getState().setError(message);
        }
      },
      stop: async () => {
        const store = useDebateStore.getState();
        const sessionId = store.sessionId;
        if (!sessionId) return;

        // Abort the SSE connection immediately
        abortRef.current?.abort();
        abortRef.current = null;

        store.markStopRequested();

        try {
          await fetch(`${API_BASE}/api/debate/stop`, {
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
    [fetchReport],
  );

  return api;
}
