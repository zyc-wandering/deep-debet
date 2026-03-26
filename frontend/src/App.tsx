import { useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useDebateStore } from "./store/debateStore";
import { useDebate } from "./hooks/useDebate";
import { DebateConfig } from "./types";
import ConfigPhase from "./components/ConfigPhase";
import ResearchPhase from "./components/ResearchPhase";
import DraftingPhase from "./components/DraftingPhase";
import ArenaPhase from "./components/ArenaPhase";
import SummaryPhase from "./components/SummaryPhase";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").trim();

async function restoreSessionFromBackend(sessionId: string, apiBase: string) {
  try {
    const resp = await fetch(`${apiBase}/api/sessions/${sessionId}`);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

function App() {
  const phase = useDebateStore((s) => s.phase);
  const sessionStatus = useDebateStore((s) => s.status);
  const sessionId = useDebateStore((s) => s.sessionId);
  const errorMessage = useDebateStore((s) => s.errorMessage);
  const reset = useDebateStore((s) => s.reset);
  const viewPhase = useDebateStore((s) => s.viewPhase);
  const setViewPhase = useDebateStore((s) => s.setViewPhase);
  const debate = useDebate();

  const displayPhase = viewPhase ?? phase;

  useEffect(() => {
    const storedId = sessionId;
    const storedStatus = sessionStatus;
    if (!storedId || storedStatus === "idle") return;
    if (storedStatus === "done" || storedStatus === "error") return;

    restoreSessionFromBackend(storedId, API_BASE).then((data) => {
      if (!data) return;
      const sessionState = data.state?.toLowerCase();
      if (sessionState === "stopped" || sessionState === "error") return;

      const messages: import("./types").TranscriptMessage[] = (data.messages || []).map(
        (m: Record<string, unknown>) => ({
          id: String(m.id),
          timestamp: new Date(String(m.created_at)),
          speaker: String(m.speaker),
          content: String(m.content),
          stage: String(m.stage || "free_debate") as import("./types").TranscriptMessage["stage"],
          turnId: Number(m.turn_index ?? 0),
        }),
      );

      const store = useDebateStore.getState();
      if (data.focus_options?.length) {
        store.setFocusOptions(storedId, data.focus_options);
      }
      if (data.debaters?.length) {
        const mainCount = data.main_count ?? data.debaters.length;
        store.setDebaters(
          storedId,
          data.debaters,
          data.deadline_at ? Date.parse(data.deadline_at) : null,
          mainCount,
        );
      }
      if (messages.length > 0) {
        messages.forEach((msg) => {
          if (!store.transcript.find((m) => m.id === msg.id)) {
            store.finalizeTurn(storedId, msg.speaker, msg.turnId, msg.content, msg.stage);
          }
        });
      }
      if (data.structured_report) {
        store.setStructuredReport(data.structured_report);
      }
      if (data.host_summary || data.structured_report?.host_conclusion) {
        store.setReportMarkdown(data.report_markdown || "");
        store.setDone(storedId, data.report_path || "");
      }
    });
  }, []);

  const handleStart = async (config: DebateConfig) => {
    await debate.start({
      topic: config.topic,
      debater_count: config.numDebaters,
      time_limit_sec: 1800,
      max_turns: config.maxRounds,
      enable_debater_search: config.enableSearch,
      debate_language: config.language,
      model_variant: config.modelVariant,
      fun_mode: "persona_clash",
    });
  };

  const phaseOrder = ["config", "research", "drafting", "arena", "summary"];
  const currentIdx = phaseOrder.indexOf(phase);

  const isNavClickable = (p: string): boolean => {
    if (p !== "arena" && p !== "summary") return false;
    if (sessionStatus !== "done") return false;
    const stepIdx = phaseOrder.indexOf(p);
    return stepIdx <= currentIdx && p !== displayPhase;
  };

  const handleNavClick = (p: string) => {
    if (!isNavClickable(p)) return;
    setViewPhase(p === phase ? null : (p as typeof phase));
  };

  if (displayPhase === "arena") {
    return (
      <div className="h-screen bg-arena text-slate-200 font-sans overflow-hidden">
        {errorMessage && <ErrorBanner message={errorMessage} onReset={reset} />}
        <ArenaPhase />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg text-slate-900 font-sans">
      <header className="flex items-center justify-between px-6 py-4 bg-white/80 backdrop-blur-md sticky top-0 z-50 border-b border-primary/10">
        <div className="flex items-center gap-4">
          <div className="w-8 h-8 flex items-center justify-center bg-primary rounded-lg text-white font-bold text-sm">
            D
          </div>
          <h2 className="text-lg font-bold">Multi-Agent Debate Room</h2>
        </div>
        <nav className="hidden md:flex items-center gap-1 text-sm font-medium">
          {(["research", "drafting", "arena", "summary"] as const).map((p, i, arr) => {
            const stepIdx = phaseOrder.indexOf(p);
            const isActive = displayPhase === p;
            const isPast = stepIdx < currentIdx;
            const clickable = isNavClickable(p);
            const label = p === "research" ? "Research" : p === "drafting" ? "Drafting" : p === "arena" ? "Arena" : "Summary";
            return (
              <div key={p} className="flex items-center gap-1">
                <div
                  className={`flex items-center gap-2 ${clickable ? "cursor-pointer group" : ""}`}
                  onClick={() => handleNavClick(p)}
                >
                  <span
                    className={`w-6 h-6 rounded-full text-xs font-bold flex items-center justify-center transition-all duration-300 ${
                      isActive
                        ? "bg-primary text-white"
                        : isPast
                          ? `bg-primary/20 text-primary ${clickable ? "group-hover:bg-primary/40" : ""}`
                          : "bg-slate-200 text-slate-400"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span
                    className={`transition-colors duration-300 ${
                      isActive
                        ? "text-primary font-bold"
                        : isPast
                          ? `text-slate-600 ${clickable ? "group-hover:text-primary" : ""}`
                          : "text-slate-400"
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {i < arr.length - 1 && (
                  <div className={`w-8 h-px mx-1 transition-colors duration-300 ${isPast ? "bg-primary/30" : "bg-slate-200"}`} />
                )}
              </div>
            );
          })}
        </nav>
      </header>

      <main className="flex-1 flex justify-center py-10 px-4">
        <div className="w-full max-w-6xl">
          {errorMessage && <ErrorBanner message={errorMessage} onReset={reset} />}

          <AnimatePresence mode="wait">
            {displayPhase === "config" && (
              <motion.div key="config" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                <ConfigPhase onStart={handleStart} />
              </motion.div>
            )}
            {displayPhase === "research" && (
              <motion.div key="research" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                <ResearchPhase />
              </motion.div>
            )}
            {displayPhase === "drafting" && (
              <motion.div key="drafting" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                <DraftingPhase />
              </motion.div>
            )}
            {displayPhase === "summary" && (
              <motion.div key="summary" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                <SummaryPhase />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}

function ErrorBanner({ message, onReset }: { message: string; onReset: () => void }) {
  return (
    <div className="mx-4 mt-4 mb-0 p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl flex items-center justify-between">
      <p className="font-medium text-sm">{message}</p>
      <button
        onClick={onReset}
        className="px-4 py-2 bg-red-100 hover:bg-red-200 rounded-lg text-sm font-bold transition-colors cursor-pointer"
      >
        重试
      </button>
    </div>
  );
}

export default App;
