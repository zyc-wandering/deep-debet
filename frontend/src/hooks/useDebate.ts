import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useCallback, useMemo, useRef } from "react";
import { DebateStartRequest, DebaterConfig } from "../types";
import { useDebateStore } from "../store/debateStore";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

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
        abortRef.current?.abort();
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        useDebateStore.getState().start();

        await fetchEventSource(`${API_BASE}/api/debate/start`, {
          method: "POST",
          openWhenHidden: true,
          signal: ctrl.signal,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          onopen: async (response) => {
            if (!response.ok) {
              throw new Error(`Failed to connect: ${response.status}`);
            }
          },
          onmessage: async (msg) => {
            if (!msg.event) return;
            if (msg.event === "host_research") {
              const data = JSON.parse(msg.data) as { chunk: string; session_id: string };
              useDebateStore.getState().appendHostResearch(data.chunk);
              const current = useDebateStore.getState().sessionId;
              if (data.session_id && !current) {
                useDebateStore.setState({ sessionId: data.session_id });
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
            if (msg.event === "debate_turn_end") {
              const data = JSON.parse(msg.data) as {
                session_id: string;
                speaker: string;
                turn_id: number;
                full_content: string;
              };
              useDebateStore.getState().finalizeTurn(
                data.session_id,
                data.speaker,
                data.turn_id,
                data.full_content,
              );
              return;
            }
            if (msg.event === "host_summary") {
              const data = JSON.parse(msg.data) as { chunk: string };
              useDebateStore.getState().appendHostSummary(data.chunk);
              return;
            }
            if (msg.event === "done") {
              const data = JSON.parse(msg.data) as { session_id: string; report_path: string };
              useDebateStore.getState().setDone(data.session_id, data.report_path);
              await fetchReport(data.report_path);
              abortRef.current?.abort();
              return;
            }
            if (msg.event === "error") {
              const data = JSON.parse(msg.data) as { message: string };
              useDebateStore.getState().setError(data.message || "Unknown error");
              abortRef.current?.abort();
            }
          },
          onerror: (error) => {
            useDebateStore.getState().setError(error.message || "Connection error");
            throw error;
          },
        });
      },
      stop: async () => {
        const sessionId = useDebateStore.getState().sessionId;
        if (!sessionId) return;
        abortRef.current?.abort();
        try {
          await fetch(`${API_BASE}/api/debate/stop`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId }),
          });
        } catch {
          // best effort stop
        }
      },
      fetchReport,
    }),
    [fetchReport],
  );

  return api;
}
