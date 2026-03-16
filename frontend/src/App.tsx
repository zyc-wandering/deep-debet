import { useDebateStore } from "./store/debateStore";
import { useDebate } from "./hooks/useDebate";
import { DebateConfig } from "./types";
import ConfigPhase from "./components/ConfigPhase";
import ResearchPhase from "./components/ResearchPhase";
import DraftingPhase from "./components/DraftingPhase";
import ArenaPhase from "./components/ArenaPhase";
import SummaryPhase from "./components/SummaryPhase";

function App() {
  const phase = useDebateStore((s) => s.phase);
  const errorMessage = useDebateStore((s) => s.errorMessage);
  const reset = useDebateStore((s) => s.reset);
  const debate = useDebate();

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

  // Arena phase is full-screen, no wrapper padding
  if (phase === "arena") {
    return (
      <div className="min-h-screen bg-arena text-slate-200 font-sans">
        {errorMessage && <ErrorBanner message={errorMessage} onReset={reset} />}
        <ArenaPhase />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg text-slate-900 font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 bg-white/80 backdrop-blur-md sticky top-0 z-50 border-b border-primary/10">
        <div className="flex items-center gap-4">
          <div className="w-8 h-8 flex items-center justify-center bg-primary rounded-lg text-white font-bold text-sm">
            D
          </div>
          <h2 className="text-lg font-bold">Multi-Agent Debate Room</h2>
        </div>
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium">
          {(["research", "drafting", "arena", "summary"] as const).map((p) => (
            <span
              key={p}
              className={
                phase === p
                  ? "text-primary border-b-2 border-primary pb-1"
                  : "text-slate-400"
              }
            >
              {p === "research"
                ? "Research"
                : p === "drafting"
                  ? "Drafting"
                  : p === "arena"
                    ? "Arena"
                    : "Summary"}
            </span>
          ))}
        </nav>
      </header>

      <main className="flex-1 flex justify-center py-10 px-4">
        <div className="w-full max-w-6xl">
          {errorMessage && <ErrorBanner message={errorMessage} onReset={reset} />}

          {phase === "config" && <ConfigPhase onStart={handleStart} />}
          {phase === "research" && <ResearchPhase />}
          {phase === "drafting" && <DraftingPhase />}
          {phase === "summary" && <SummaryPhase />}
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
