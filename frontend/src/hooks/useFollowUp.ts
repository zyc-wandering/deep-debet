import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useCallback, useRef } from "react";
import { FollowUpRequest, TraceEntry, TraceMeta } from "../types";
import { useDebateStore } from "../store/debateStore";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").trim();

type TraceAwarePayload = {
  session_id?: string;
  _trace?: TraceMeta;
  [key: string]: unknown;
};

function buildTraceEntry(event: string, data: TraceAwarePayload, trace: TraceMeta): TraceEntry {
  return {
    id: `${trace.trace_id}-${trace.event_seq}`,
    event,
    session_id: typeof data.session_id === "string" ? data.session_id : undefined,
    trace,
    summary: event.replaceAll("_", " "),
  };
}

export function useFollowUp() {
  const abortRef = useRef<AbortController | null>(null);

  const submitFollowUp = useCallback(async (payload: FollowUpRequest) => {
    const store = useDebateStore.getState();

    // Don't allow switching targets while streaming
    if (store.isFollowUpStreaming) {
      return;
    }

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    // Add message to store
    const messageId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    store.addFollowUpMessage({
      id: messageId,
      target_role: payload.target_role,
      question: payload.question,
      response: "",
      created_at: new Date().toISOString(),
      isStreaming: true,
    });
    store.setFollowUpTarget(payload.target_role);
    store.setFollowUpStreaming(true);

    try {
      await fetchEventSource(`${API_BASE}/api/debate/followup`, {
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
          const data = (msg.data ? (JSON.parse(msg.data) as TraceAwarePayload) : {}) as TraceAwarePayload;
          const trace = data._trace;
          if (trace) {
            useDebateStore.getState().addTraceEntry(buildTraceEntry(msg.event, data, trace));
            if (typeof trace.journal_path === "string" && trace.journal_path) {
              useDebateStore.getState().setTraceJournalPath(trace.journal_path);
            }
          }

          if (msg.event === "follow_up_token") {
            const tokenData = data as {
              session_id: string;
              follow_up_id: string;
              target_role: string;
              token: string;
            };
            useDebateStore.getState().appendFollowUpToken(tokenData.follow_up_id, tokenData.token);
            return;
          }

          if (msg.event === "follow_up_end") {
            const endData = data as {
              session_id: string;
              follow_up_id: string;
              target_role: string;
              full_response: string;
            };
            useDebateStore.getState().finalizeFollowUp(endData.follow_up_id, endData.full_response);
            abortRef.current?.abort();
            abortRef.current = null;
            return;
          }

          if (msg.event === "error") {
            const errorData = data as { message: string };
            useDebateStore.getState().setError(errorData.message || "Follow-up error");
            useDebateStore.getState().setFollowUpStreaming(false);
            abortRef.current = null;
          }
        },
        onerror: (error) => {
          if (ctrl.signal.aborted) {
            return;
          }
          useDebateStore.getState().setError(error.message || "Connection error");
          useDebateStore.getState().setFollowUpStreaming(false);
          throw error;
        },
      });
    } catch (error) {
      if (ctrl.signal.aborted) {
        return;
      }
      const message = error instanceof Error ? error.message : "Connection error";
      useDebateStore.getState().setError(message);
      useDebateStore.getState().setFollowUpStreaming(false);
    }
  }, []);

  const stopFollowUp = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    useDebateStore.getState().setFollowUpStreaming(false);
  }, []);

  return { submitFollowUp, stopFollowUp };
}
