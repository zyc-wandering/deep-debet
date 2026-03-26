import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Search, FileText, Lightbulb, Zap, Loader2, Users } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { useDebateStore } from "../store/debateStore";
import { useDebate } from "../hooks/useDebate";
import { FocusOption } from "../types";

export default function ResearchPhase() {
  const hostResearch = useDebateStore((s) => s.hostResearch);
  const focusOptions = useDebateStore((s) => s.focusOptions);
  const selectedFocusId = useDebateStore((s) => s.selectedFocusId);
  const sessionId = useDebateStore((s) => s.sessionId);
  const isConfigurationReady = useDebateStore((s) => s.isConfigurationReady);
  const intensityDraft = useDebateStore((s) => s.intensityDraft);
  const userContextDraft = useDebateStore((s) => s.userContextDraft);
  const debateLanguage = useDebateStore((s) => s.debateLanguage);
  const setSelectedFocus = useDebateStore((s) => s.setSelectedFocus);
  const setIntensityDraft = useDebateStore((s) => s.setIntensityDraft);
  const setUserContextDraft = useDebateStore((s) => s.setUserContextDraft);

  const { configure } = useDebate();

  const [progress, setProgress] = useState(0);
  const [isAssembling, setIsAssembling] = useState(false);
  const [assembleStep, setAssembleStep] = useState(0);
  const isZh = debateLanguage === "zh";

  useEffect(() => {
    if (!isConfigurationReady) {
      const interval = setInterval(() => {
        setProgress((p) => Math.min(p + 3, 95));
      }, 500);
      return () => clearInterval(interval);
    } else {
      setProgress(100);
    }
  }, [isConfigurationReady]);

  // Timed step progression during assembling
  useEffect(() => {
    if (!isAssembling) return;
    const timers = [
      setTimeout(() => setAssembleStep(1), 4000),
      setTimeout(() => setAssembleStep(2), 8000),
    ];
    return () => timers.forEach(clearTimeout);
  }, [isAssembling]);

  const handleConfigure = () => {
    if (!selectedFocusId || !sessionId) return;
    setIsAssembling(true);
    configure({
      session_id: sessionId,
      pre_debate_config: {
        selected_focus_id: selectedFocusId,
        intensity: intensityDraft,
        user_context: userContextDraft,
      },
    });
  };

  // Assembling overlay — shown after user clicks configure until debaters_ready arrives
  if (isAssembling) {
    const assemblingSteps = isZh
      ? [
          "正在生成辩手角色…",
          "正在创建候选替补…",
          "正在生成辩手形象…",
        ]
      : [
          "Generating debater personas…",
          "Creating substitute candidates…",
          "Generating avatars & visuals…",
        ];

    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col items-center justify-center min-h-[60vh] gap-8"
      >
        <motion.div
          animate={{ scale: [1, 1.08, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        >
          <Users className="w-16 h-16 text-primary" />
        </motion.div>

        <div className="text-center">
          <h2 className="text-3xl font-black tracking-tight mb-2">
            {isZh ? "正在组建辩手阵容" : "Assembling Debate Panel"}
          </h2>
          <p className="text-slate-500 text-lg max-w-md">
            {isZh
              ? "AI 主持人正在为您精选主力辩手和候选替补…"
              : "The AI moderator is selecting your main lineup and substitutes…"}
          </p>
        </div>

        <div className="flex flex-col gap-3 w-full max-w-sm">
          {assemblingSteps.map((label, i) => {
            const isDone = assembleStep > i;
            const isActive = assembleStep === i;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.3 }}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isDone
                    ? "bg-green-50 border border-green-200"
                    : isActive
                      ? "bg-primary/5 border border-primary/20"
                      : "bg-slate-50 border border-slate-100"
                }`}
              >
                {isDone ? (
                  <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center">
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                ) : isActive ? (
                  <Loader2 className="w-5 h-5 text-primary animate-spin" />
                ) : (
                  <div className="w-5 h-5 rounded-full border-2 border-slate-200" />
                )}
                <span
                  className={`text-sm font-medium ${
                    isDone ? "text-green-700" : isActive ? "text-primary" : "text-slate-400"
                  }`}
                >
                  {label}
                </span>
              </motion.div>
            );
          })}
        </div>

        <div className="w-full max-w-sm">
          <div className="h-1.5 rounded-full bg-primary/10 overflow-hidden">
            <motion.div
              className="h-full bg-primary rounded-full"
              initial={{ width: "5%" }}
              animate={{ width: "75%" }}
              transition={{ duration: 20, ease: "linear" }}
            />
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <div className="flex flex-col max-w-4xl mx-auto gap-6">
      {/* Status bar */}
      <div className="flex flex-wrap justify-between gap-4 p-6 bg-white rounded-xl shadow-sm border border-primary/10">
        <div className="flex min-w-72 flex-col gap-2">
          <div className="flex items-center gap-2 text-primary">
            <Search className="w-5 h-5 animate-pulse" />
            <span className="text-sm font-bold uppercase tracking-wider">
              {isZh ? "主持人调研中" : "Active Analysis"}
            </span>
          </div>
          <h1 className="text-4xl font-black leading-tight tracking-tight">
            {isZh ? "主持人正在调研" : "Moderator Researching"}
          </h1>
          <p className="text-slate-500 text-base max-w-xl">
            {isZh
              ? "AI 主持人正在解析权威资料、白皮书和历史辩论记录，为本场辩论构建知识框架。"
              : "Our AI Moderator is parsing high-authority sources to frame the session."}
          </p>
        </div>
        <div className="w-full mt-4">
          <div className="flex gap-6 justify-between mb-2">
            <p className="text-sm font-bold">
              {isZh ? "正在综合全局调研结果" : "Synthesizing global research findings"}
            </p>
            <p className="text-primary text-sm font-bold">{progress}%</p>
          </div>
          <div className="h-3 rounded-full bg-primary/10 overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* Research content */}
      <AnimatePresence>
        {hostResearch && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-8"
          >
            <section className="p-6 bg-white rounded-xl shadow-sm border border-primary/5">
              <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
                <FileText className="text-primary w-6 h-6" />
                {isZh ? "背景与上下文" : "Background & Context"}
              </h2>
              <div className="prose prose-slate max-w-none border-l-4 border-primary/20 pl-6 py-2">
                <Markdown remarkPlugins={[remarkGfm]}>{hostResearch}</Markdown>
              </div>
            </section>

            {/* Focus options */}
            {isConfigurationReady && focusOptions.length > 0 && (
              <motion.section
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <div className="flex flex-col gap-2 mb-6">
                  <h2 className="text-2xl font-bold tracking-tight">
                    {isZh ? "选择讨论切面" : "Select Debate Angle"}
                  </h2>
                  <p className="text-slate-500">
                    {isZh
                      ? "缩小讨论焦点，确保 AI 智能体进行高质量讨论。"
                      : "Narrow the focus for a high-quality discussion."}
                  </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {focusOptions.map((opt: FocusOption) => (
                    <motion.div
                      key={opt.id}
                      whileHover={{ scale: 1.01 }}
                      whileTap={{ scale: 0.98 }}
                      transition={{ type: "tween", duration: 0.15 }}
                      onClick={() => setSelectedFocus(opt.id)}
                      className={`cursor-pointer bg-white border-2 rounded-xl p-5 transition-all shadow-sm flex flex-col gap-4 ${
                        selectedFocusId === opt.id
                          ? "border-primary ring-2 ring-primary/20"
                          : "border-primary/10 hover:border-primary/50"
                      }`}
                    >
                      <div
                        className={`w-12 h-12 rounded-lg flex items-center justify-center transition-colors ${
                          selectedFocusId === opt.id
                            ? "bg-primary text-white"
                            : "bg-primary/10 text-primary"
                        }`}
                      >
                        <Lightbulb className="w-6 h-6" />
                      </div>
                      <div>
                        <h3 className="font-bold text-lg mb-1">{opt.name}</h3>
                        <p className="text-slate-500 text-sm leading-snug">{opt.description}</p>
                      </div>
                    </motion.div>
                  ))}
                </div>

                {/* Intensity selector */}
                <div className="mt-6 p-5 bg-white rounded-xl border border-primary/10">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap className="text-primary w-5 h-5" />
                    <span className="font-semibold">{isZh ? "辩论强度" : "Debate Intensity"}</span>
                  </div>
                  <div className="flex h-11 items-center rounded-lg bg-primary/5 p-1 border border-primary/10">
                    {(["mild", "balanced", "intense"] as const).map((level) => (
                      <button
                        key={level}
                        onClick={() => setIntensityDraft(level)}
                        className={`flex-1 h-full rounded-md text-sm font-medium transition-all ${
                          intensityDraft === level
                            ? "bg-primary text-white shadow-sm"
                            : "text-slate-500 hover:text-slate-700 hover:bg-primary/5"
                        }`}
                      >
                        {level === "mild"
                          ? isZh ? "温和" : "Mild"
                          : level === "balanced"
                            ? isZh ? "均衡" : "Balanced"
                            : isZh ? "激烈" : "Intense"}
                      </button>
                    ))}
                  </div>

                  {/* User context */}
                  <div className="mt-4">
                    <textarea
                      className="w-full resize-none rounded-lg border border-primary/15 bg-bg/50 p-3 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-primary/30"
                      placeholder={
                        isZh
                          ? "可选：补充背景信息或你特别关心的点..."
                          : "Optional: add context or specific concerns..."
                      }
                      value={userContextDraft}
                      onChange={(e) => setUserContextDraft(e.target.value)}
                    />
                  </div>
                </div>

                {/* Action bar */}
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 }}
                  className="flex justify-between items-center p-6 bg-primary/5 rounded-xl border border-primary/10 mt-6"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                    <span className="text-slate-600 text-sm font-medium italic">
                      {selectedFocusId
                        ? isZh ? "切面已选择，准备就绪。" : "Angle selected. Ready to proceed."
                        : isZh ? "请选择一个切面..." : "Select an angle to proceed..."}
                    </span>
                  </div>
                  <button
                    onClick={handleConfigure}
                    disabled={!selectedFocusId}
                    className="bg-primary hover:bg-primary/90 text-white px-8 py-3 rounded-lg font-bold transition-all shadow-lg shadow-primary/20 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
                  >
                    {isZh ? "组建辩手阵容" : "Assemble Debate Panel"}
                  </button>
                </motion.div>
              </motion.section>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
