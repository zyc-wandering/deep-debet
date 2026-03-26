import { useEffect, useRef } from "react";
import { Mic, Quote, History, StopCircle, ArrowLeft } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useDebateStore } from "../store/debateStore";
import { useDebate } from "../hooks/useDebate";
import Avatar from "./Avatar";
import { useResizablePanels, DragHandle } from "./ResizablePanel";

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
  const viewPhase = useDebateStore((s) => s.viewPhase);
  const setViewPhase = useDebateStore((s) => s.setViewPhase);

  const isReview = viewPhase === "arena";

  const { stop } = useDebate();
  const transcriptRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const isZh = debateLanguage === "zh";
  const isFreeDebateStage = currentStage === "free_debate";

  const { widths, handleMouseDown } = useResizablePanels({
    initialWidths: [25, 45, 30],
    minWidthsPx: [200, 300, 200],
    containerRef,
  });

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript, liveBuffers]);

  const activeDebater = allDebaters.find((d) => d.name === activeSpeaker);
  const preparingDebater = preparingTurn
    ? allDebaters.find((d) => d.name === preparingTurn.speaker)
    : null;
  const spotlightDebater = isReview ? null : (activeDebater || preparingDebater);

  const liveContent = isReview
    ? ""
    : Object.entries(liveBuffers)
        .filter(([key]) => key.startsWith(`${activeSpeaker}-`))
        .map(([, val]) => val.content)
        .join("");

  const freeDebateTurns = lines.filter((l) => l.stage === "free_debate").length;

  const lastContentBySpeaker: Record<string, string> = {};
  for (const msg of transcript) {
    lastContentBySpeaker[msg.speaker] = msg.content;
  }

  const stageLabel = isReview
    ? isZh ? "回顾模式" : "Review"
    : currentStage === "opening"
      ? isZh ? "开场陈述" : "Opening"
      : currentStage === "free_debate"
        ? isZh ? "自由辩论" : "Free Debate"
        : currentStage === "closing"
          ? isZh ? "总结陈词" : "Closing"
          : isZh ? "进行中" : "In Progress";

  // Shrunk font sizes (one step smaller than before)
  const freeDebateTextSizeClass = isFreeDebateStage ? "text-[11px] md:text-xs" : "text-xs md:text-sm";
  const freeDebateContentSizeClass = isFreeDebateStage ? "text-xs md:text-sm" : "text-sm md:text-base";
  const speakingDebaters = allDebaters.filter(
    (d) => !d.stance.toLowerCase().includes("非正式"),
  );

  return (
    <div ref={containerRef} className="flex flex-col lg:flex-row h-screen bg-arena text-slate-200 overflow-hidden font-sans">
      {/* Left Column: Speaker Profile */}
      <div
        className="hidden lg:flex flex-col items-center justify-center p-6 border-r border-slate-800/60 relative z-10 shrink-0"
        style={{ width: `${widths[0]}%` }}
      >
        {spotlightDebater ? (
          <motion.div
            key={spotlightDebater.id}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, type: "tween", ease: "easeOut" }}
            className="flex flex-col items-center w-full max-w-sm"
          >
            <div className="relative mb-6">
              <div className="absolute -inset-6 bg-primary/20 rounded-full blur-3xl animate-pulse" />
              <Avatar
                debater={spotlightDebater}
                size="xl"
                className="border-4 border-primary shadow-[0_0_60px_rgba(212,98,17,0.3)] relative z-10"
              />
              <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 bg-primary text-white px-5 py-1.5 rounded-full shadow-xl flex items-center gap-2 border-2 border-slate-900 whitespace-nowrap z-20">
                <Mic className="w-3.5 h-3.5 animate-pulse" />
                <span className="text-xs font-bold uppercase tracking-wider">
                  {isZh ? "发言中" : "Speaking"}
                </span>
              </div>
            </div>
            <div className="text-center">
              <h2 className="text-2xl font-black text-white mb-1">{spotlightDebater.name}</h2>
              <p className="text-primary font-bold uppercase tracking-widest text-xs mb-4">
                {spotlightDebater.stance}
              </p>
              <p className="text-slate-400 text-xs leading-relaxed line-clamp-3 px-2">
                {spotlightDebater.background}
              </p>
            </div>
          </motion.div>
        ) : allDebaters.length > 0 ? (
          <div className="flex flex-col items-center justify-center w-full max-w-sm">
            <Avatar
              debater={allDebaters[0]}
              className="border-4 border-slate-700 opacity-40"
            />
            <p className="text-slate-600 text-sm mt-4 italic">
              {isReview
                ? isZh ? "辩论已结束" : "Debate finished"
                : isZh ? "等待辩手就位..." : "Waiting for speakers..."}
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center w-full max-w-sm">
            <p className="text-slate-600 text-sm italic">
              {isZh ? "等待辩手就位..." : "Waiting for speakers..."}
            </p>
          </div>
        )}
      </div>

      {/* Drag Handle: Left | Middle */}
      <DragHandle onMouseDown={(e) => handleMouseDown(0, e)} />

      {/* Middle Column: Live Speech */}
      <div
        className="flex-1 lg:flex-none flex flex-col relative z-10 min-w-0"
        style={{ width: `${widths[1]}%` }}
      >
        {/* Header */}
        <div className="h-16 border-b border-slate-800/60 bg-slate-900/50 flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-4 min-w-0">
            <div className={`px-3 py-1 text-white text-xs font-bold rounded-full uppercase tracking-wider shrink-0 ${isReview ? "bg-slate-600" : "bg-primary"}`}>
              {stageLabel}
            </div>
            <div className="text-sm font-medium text-slate-300 truncate min-w-0" title={topic}>
              {topic}
            </div>
          </div>
          <div className="flex items-center gap-4 shrink-0">
            {!isReview && currentStage === "free_debate" && (
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
                  {isZh ? "轮次" : "Round"}
                </span>
                <span className="text-sm font-bold text-white bg-slate-800 px-3 py-1 rounded-md">
                  {freeDebateTurns}
                </span>
              </div>
            )}
            {!isReview && status === "running" && (
              <button
                onClick={stop}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 text-xs font-bold hover:bg-red-500/30 transition-colors cursor-pointer"
              >
                <StopCircle className="w-3.5 h-3.5" />
                {isZh ? "终止" : "Stop"}
              </button>
            )}
            {isReview && (
              <button
                onClick={() => setViewPhase(null)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300 text-xs font-bold hover:bg-slate-600 transition-colors cursor-pointer"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                {isZh ? "返回总结" : "Back to Summary"}
              </button>
            )}
          </div>
        </div>

        {/* Mobile: speaker profile on top */}
        {!isReview && (
          <div className="lg:hidden flex items-center gap-4 p-4 border-b border-slate-800/40 bg-slate-900/30">
            {spotlightDebater && (
              <>
                <Avatar debater={spotlightDebater} size="md" className="border-2 border-primary shrink-0" />
                <div className="flex flex-col min-w-0">
                  <span className="text-sm font-bold text-white truncate">{spotlightDebater.name}</span>
                  <span className="text-xs text-primary truncate">{spotlightDebater.stance}</span>
                </div>
              </>
            )}
          </div>
        )}

        {/* Speech content area */}
        <div className="flex-1 flex flex-col items-center justify-center p-4 md:p-6 overflow-y-auto">
          {isReview ? (
            <div className="w-full max-w-2xl flex flex-col items-center justify-center min-h-[150px] gap-4">
              <div className="px-4 py-2 bg-primary/20 text-primary rounded-full text-sm font-bold">
                {isZh ? "回顾模式" : "Review Mode"}
              </div>
              <p className="text-slate-500 text-sm text-center">
                {isZh ? "请在右侧面板浏览完整辩论记录" : "Browse the full transcript in the right panel"}
              </p>
              <p className="text-slate-600 text-xs">
                {isZh ? `共 ${transcript.length} 条发言` : `${transcript.length} total entries`}
              </p>
            </div>
          ) : (
            <AnimatePresence mode="wait">
              {preparingTurn && !liveContent ? (
                <motion.div
                  key="preparing"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="w-full max-w-3xl"
                >
                  <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-8 flex flex-col items-center justify-center min-h-[180px]">
                    <div className="flex gap-3 mb-4">
                      <div className="w-3 h-3 bg-primary rounded-full animate-bounce" />
                      <div className="w-3 h-3 bg-primary rounded-full animate-bounce" style={{ animationDelay: "0.15s" }} />
                      <div className="w-3 h-3 bg-primary rounded-full animate-bounce" style={{ animationDelay: "0.3s" }} />
                    </div>
                    <p className="text-slate-400 text-sm font-medium animate-pulse">
                      {isZh ? "正在组织论点..." : "Formulating argument..."}
                    </p>
                  </div>
                </motion.div>
              ) : liveContent ? (
                <motion.div
                  key={`live-${activeSpeaker}-${preparingTurn?.turnId ?? "none"}`}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className="w-full max-w-3xl"
                >
                  <div className="bg-slate-800/80 backdrop-blur-xl border border-slate-700 rounded-2xl p-6 md:p-8 shadow-2xl relative">
                    <Quote className="absolute top-6 left-6 w-12 h-12 text-slate-700/40 rotate-180 -z-10" />
                    <div
                      className={`leading-relaxed text-slate-100 font-serif relative z-10 prose prose-invert max-w-none prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 prose-headings:text-slate-100 ${freeDebateContentSizeClass}`}
                    >
                      <Markdown remarkPlugins={[remarkGfm]}>{liveContent}</Markdown>
                    </div>
                  </div>
                </motion.div>
              ) : activeSpeaker && lastContentBySpeaker[activeSpeaker] ? (
                <motion.div
                  key={`last-${activeSpeaker}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="w-full max-w-3xl"
                >
                  <div className="bg-slate-800/40 border border-slate-700/30 rounded-2xl p-6 md:p-8 relative">
                    <Quote className="absolute top-6 left-6 w-12 h-12 text-slate-700/30 rotate-180 -z-10" />
                    <div className="text-xs text-slate-500 mb-3 font-medium uppercase tracking-wider">
                      {activeSpeaker} · {isZh ? "上一轮发言" : "Previous turn"}
                    </div>
                    <div
                      className={`leading-relaxed text-slate-300 font-serif relative z-10 prose prose-invert max-w-none prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 ${freeDebateTextSizeClass}`}
                    >
                      <Markdown remarkPlugins={[remarkGfm]}>{lastContentBySpeaker[activeSpeaker]}</Markdown>
                    </div>
                  </div>
                </motion.div>
              ) : transcript.length > 0 ? (
                <div className="w-full max-w-2xl flex items-center justify-center min-h-[150px]">
                  <p className="text-slate-500 text-base italic">
                    {isZh ? "等待下一位发言..." : "Waiting for next speaker..."}
                  </p>
                </div>
              ) : (
                <div className="w-full max-w-2xl flex items-center justify-center min-h-[150px]">
                  <p className="text-slate-600 text-base italic">
                    {isZh ? "辩论即将开始..." : "Debate starting soon..."}
                  </p>
                </div>
              )}
            </AnimatePresence>
          )}
        </div>

        {/* Bench / Roster */}
        <div className="h-24 border-t border-slate-800/60 bg-slate-900/80 backdrop-blur-md flex items-center justify-start md:justify-center gap-3 px-6 overflow-x-auto shrink-0">
          {speakingDebaters.map((agent) => {
            const isActive = !isReview && agent.name === activeSpeaker;
            return (
              <div
                key={agent.id}
                className={`relative flex items-center gap-3 p-3 rounded-xl border transition-all duration-300 min-w-[140px] ${
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
                    {isReview
                      ? agent.stance
                      : isActive
                        ? isZh ? "发言中" : "Speaking"
                        : isZh ? "等待中" : "Waiting"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="absolute inset-0 pointer-events-none z-0">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,_rgba(212,98,17,0.08)_0%,_transparent_50%),_radial-gradient(circle_at_50%_80%,_rgba(212,98,17,0.04)_0%,_transparent_60%)]" />
        </div>
      </div>

      {/* Drag Handle: Middle | Right */}
      <DragHandle onMouseDown={(e) => handleMouseDown(1, e)} />

      {/* Right Column: Transcript History */}
      <div
        className="hidden lg:flex bg-slate-900 border-l border-slate-800 flex-col shrink-0 z-30 shadow-2xl"
        style={{ width: `${widths[2]}%` }}
      >
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50 backdrop-blur-md shrink-0">
          <div className="flex items-center gap-2">
            <History className="text-primary w-4 h-4" />
            <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider">
              {isZh ? "发言记录" : "Transcript"}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {isReview ? (
              <span className="text-[10px] text-slate-500 font-mono">COMPLETE</span>
            ) : (
              <>
                <span className="text-[10px] text-slate-500 font-mono">REC</span>
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
              </>
            )}
          </div>
        </div>

        <div ref={transcriptRef} className="flex-1 overflow-y-auto p-5 space-y-5 scroll-smooth">
          {transcript.map((msg, idx) => {
            const isLatest = idx === transcript.length - 1;
            const isMsgActive = !isReview && msg.speaker === activeSpeaker;
            return (
              <div
                key={msg.id}
                className={`flex gap-3 ${
                  isReview
                    ? "opacity-90 hover:opacity-100 transition-opacity"
                    : isMsgActive && isLatest
                      ? "opacity-100"
                      : "opacity-70 hover:opacity-100 transition-opacity"
                }`}
              >
                <span className="text-[10px] font-mono text-slate-600 shrink-0 w-10 pt-0.5">
                  {msg.timestamp.toLocaleTimeString([], {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span
                    className={`text-xs font-bold ${
                      isReview
                        ? "text-slate-300"
                        : isMsgActive && isLatest
                          ? "text-primary"
                          : isMsgActive
                            ? "text-slate-300"
                            : "text-slate-500"
                    }`}
                  >
                    {msg.speaker}
                  </span>
                  <div
                    className={`leading-relaxed font-serif relative prose prose-invert max-w-none prose-p:my-0.5 prose-ul:my-0 prose-ol:my-0 prose-li:my-0 prose-headings:text-inherit transition-all duration-300 ${
                      isReview
                        ? "text-slate-300 text-xs"
                        : isMsgActive && isLatest
                          ? "text-slate-200 text-sm"
                          : "text-slate-500 text-xs"
                    }`}
                  >
                    <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
