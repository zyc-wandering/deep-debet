import { useEffect, useRef } from "react";
import { Mic, Quote, History, StopCircle } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { useDebateStore } from "../store/debateStore";
import { useDebate } from "../hooks/useDebate";
import Avatar from "./Avatar";

export default function ArenaPhase() {
  const debaters = useDebateStore((s) => s.debaters);
  const substituteDebaters = useDebateStore((s) => s.substituteDebaters);
  const allDebaters = [...debaters, ...substituteDebaters];
  const activeSpeaker = useDebateStore((s) => s.activeSpeaker);
  const preparingTurn = useDebateStore((s) => s.preparingTurn);
  const liveBuffers = useDebateStore((s) => s.liveBuffers);
  const transcript = useDebateStore((s) => s.transcript);
  const currentStage = useDebateStore((s) => s.currentStage);
  const topic = useDebateStore((s) => s.topic);
  const debateLanguage = useDebateStore((s) => s.debateLanguage);
  const lines = useDebateStore((s) => s.lines);
  const status = useDebateStore((s) => s.status);

  const { stop } = useDebate();
  const transcriptRef = useRef<HTMLDivElement>(null);
  const isZh = debateLanguage === "zh";

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript, liveBuffers]);

  // Find active debater
  const activeDebater = allDebaters.find((d) => d.name === activeSpeaker);
  const preparingDebater = preparingTurn
    ? allDebaters.find((d) => d.name === preparingTurn.speaker)
    : null;
  const spotlightDebater = activeDebater || preparingDebater;

  // Get live content for current speaker
  const liveContent = Object.entries(liveBuffers)
    .filter(([key]) => key.startsWith(`${activeSpeaker}-`))
    .map(([, val]) => val.content)
    .join("");

  // Count rounds (free_debate turns)
  const freeDebateTurns = lines.filter((l) => l.stage === "free_debate").length;

  const stageLabel =
    currentStage === "opening"
      ? isZh ? "开场陈述" : "Opening"
      : currentStage === "free_debate"
        ? isZh ? "自由辩论" : "Free Debate"
        : currentStage === "closing"
          ? isZh ? "总结陈词" : "Closing"
          : isZh ? "进行中" : "In Progress";

  return (
    <div className="flex flex-col lg:flex-row h-[calc(100vh-80px)] -mt-6 -mx-4 bg-arena text-slate-200 overflow-hidden font-sans">
      {/* Main Arena */}
      <div className="flex-1 flex flex-col relative">
        {/* Header */}
        <div className="h-16 border-b border-slate-800/60 bg-slate-900/50 flex items-center justify-between px-6 z-10">
          <div className="flex items-center gap-4">
            <div className="px-3 py-1 bg-primary text-white text-xs font-bold rounded-full uppercase tracking-wider">
              {stageLabel}
            </div>
            <div className="text-sm font-medium text-slate-300 truncate max-w-md" title={topic}>
              {topic}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {currentStage === "free_debate" && (
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
                  {isZh ? "轮次" : "Round"}
                </span>
                <span className="text-sm font-bold text-white bg-slate-800 px-3 py-1 rounded-md">
                  {freeDebateTurns}
                </span>
              </div>
            )}
            {status === "running" && (
              <button
                onClick={stop}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 text-xs font-bold hover:bg-red-500/30 transition-colors cursor-pointer"
              >
                <StopCircle className="w-3.5 h-3.5" />
                {isZh ? "终止" : "Stop"}
              </button>
            )}
          </div>
        </div>

        {/* Spotlight Area */}
        <div className="flex-1 flex flex-col md:flex-row items-center justify-center p-6 md:p-12 gap-8 md:gap-16 relative z-10 overflow-y-auto">
          {/* Active Speaker Profile */}
          {spotlightDebater && (
            <AnimatePresence mode="wait">
              <motion.div
                key={spotlightDebater.id}
                initial={{ opacity: 0, x: -50, scale: 0.9 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 50, scale: 0.9 }}
                transition={{ duration: 0.5, type: "spring" }}
                className="flex flex-col items-center w-full md:w-1/3 max-w-sm shrink-0"
              >
                <div className="relative">
                  <div className="absolute -inset-4 bg-primary/20 rounded-full blur-2xl animate-pulse" />
                  <Avatar
                    debater={spotlightDebater}
                    size="xl"
                    className="border-4 border-primary shadow-[0_0_40px_rgba(212,98,17,0.3)]"
                  />
                  <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 bg-primary text-white px-6 py-2 rounded-full shadow-xl flex items-center gap-2 border-2 border-slate-900">
                    <Mic className="w-4 h-4 animate-pulse" />
                    <span className="text-sm font-bold uppercase tracking-wider">
                      {isZh ? "发言中" : "Speaking"}
                    </span>
                  </div>
                </div>
                <div className="mt-8 text-center">
                  <h2 className="text-3xl font-black text-white mb-2">{spotlightDebater.name}</h2>
                  <p className="text-primary font-bold uppercase tracking-widest text-sm">
                    {spotlightDebater.stance}
                  </p>
                </div>
              </motion.div>
            </AnimatePresence>
          )}

          {/* Speech Content */}
          <div className="flex-1 w-full max-w-2xl flex flex-col justify-center">
            {preparingTurn && !liveContent ? (
              <div className="bg-slate-800/50 border border-slate-700/50 rounded-3xl p-8 md:p-12 flex flex-col items-center justify-center min-h-[250px]">
                <div className="flex gap-3 mb-4">
                  <div className="w-4 h-4 bg-primary rounded-full animate-bounce" />
                  <div
                    className="w-4 h-4 bg-primary rounded-full animate-bounce"
                    style={{ animationDelay: "0.15s" }}
                  />
                  <div
                    className="w-4 h-4 bg-primary rounded-full animate-bounce"
                    style={{ animationDelay: "0.3s" }}
                  />
                </div>
                <p className="text-slate-400 font-medium animate-pulse">
                  {isZh ? "正在组织论点..." : "Formulating argument..."}
                </p>
              </div>
            ) : liveContent ? (
              <AnimatePresence mode="wait">
                <motion.div
                  key={`live-${activeSpeaker}`}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.2 }}
                  className="bg-slate-800/80 backdrop-blur-xl border border-slate-700 rounded-3xl p-8 md:p-12 shadow-2xl relative"
                >
                  <Quote className="absolute top-8 left-8 w-16 h-16 text-slate-700/50 rotate-180 -z-10" />
                  <p className="text-xl md:text-2xl leading-relaxed text-slate-100 font-serif relative z-10 whitespace-pre-wrap">
                    &ldquo;{liveContent}&rdquo;
                  </p>
                </motion.div>
              </AnimatePresence>
            ) : transcript.length > 0 ? (
              <div className="bg-slate-800/40 border border-slate-700/30 rounded-3xl p-8 md:p-12 flex items-center justify-center min-h-[200px]">
                <p className="text-slate-500 text-lg italic">
                  {isZh ? "等待下一位发言..." : "Waiting for next speaker..."}
                </p>
              </div>
            ) : null}
          </div>
        </div>

        {/* Bench / Roster */}
        <div className="h-28 border-t border-slate-800/60 bg-slate-900/80 backdrop-blur-md flex items-center justify-start md:justify-center gap-3 px-6 overflow-x-auto z-20 shrink-0">
          {allDebaters.map((agent) => {
            const isActive = agent.name === activeSpeaker;
            return (
              <div
                key={agent.id}
                className={`relative flex items-center gap-3 p-3 rounded-2xl border transition-all duration-300 min-w-[180px] ${
                  isActive
                    ? "border-primary bg-primary/10 shadow-[0_0_20px_rgba(212,98,17,0.2)]"
                    : "border-slate-800 bg-slate-950/50 opacity-60 hover:opacity-100"
                }`}
              >
                <Avatar
                  debater={agent}
                  size="sm"
                  className={`border-2 ${isActive ? "border-primary" : "border-slate-700"}`}
                />
                <div className="flex flex-col overflow-hidden">
                  <span className="text-sm font-bold text-white truncate">{agent.name}</span>
                  <span
                    className={`text-[10px] uppercase tracking-wider truncate ${
                      isActive ? "text-primary" : "text-slate-500"
                    }`}
                  >
                    {isActive
                      ? isZh ? "发言中" : "Speaking"
                      : isZh ? "等待中" : "Waiting"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Background Effects */}
        <div className="absolute inset-0 pointer-events-none z-0">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,_rgba(212,98,17,0.05),_transparent_70%)]" />
        </div>
      </div>

      {/* Right Sidebar: Transcript */}
      <div className="w-full lg:w-96 bg-slate-900 border-l border-slate-800 flex flex-col shrink-0 z-30 shadow-2xl">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <History className="text-primary w-4 h-4" />
            <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider">
              {isZh ? "实时记录" : "Live Transcript"}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 font-mono">REC</span>
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          </div>
        </div>

        <div ref={transcriptRef} className="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth">
          {transcript.map((msg, idx) => {
            const isLatest = idx === transcript.length - 1;
            return (
              <div
                key={msg.id}
                className={`flex gap-4 ${
                  isLatest ? "opacity-100" : "opacity-60 hover:opacity-100 transition-opacity"
                }`}
              >
                <span className="text-[10px] font-mono text-slate-500 shrink-0 w-12 pt-1">
                  {msg.timestamp.toLocaleTimeString([], {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <div className="flex flex-col gap-1">
                  <span
                    className={`text-xs font-bold ${
                      isLatest ? "text-primary" : "text-slate-300"
                    }`}
                  >
                    {msg.speaker}
                  </span>
                  <p
                    className={`text-sm leading-relaxed ${
                      isLatest ? "text-slate-200" : "text-slate-400"
                    }`}
                  >
                    {msg.content}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
