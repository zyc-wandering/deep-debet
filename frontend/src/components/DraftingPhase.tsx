import { useState } from "react";
import { Users, UserSearch, ArrowRightLeft, Rocket } from "lucide-react";
import { motion } from "motion/react";
import { useDebateStore } from "../store/debateStore";
import { useDebate } from "../hooks/useDebate";
import Avatar from "./Avatar";

export default function DraftingPhase() {
  const debaters = useDebateStore((s) => s.debaters);
  const substituteDebaters = useDebateStore((s) => s.substituteDebaters);
  const swapDebater = useDebateStore((s) => s.swapDebater);
  const sessionId = useDebateStore((s) => s.sessionId);
  const debateLanguage = useDebateStore((s) => s.debateLanguage);

  const { confirm } = useDebate();
  const isZh = debateLanguage === "zh";
  const [openSwapIdx, setOpenSwapIdx] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);

  const handleStart = () => {
    if (!sessionId || confirming) return;
    setConfirming(true);
    // Send confirmed debater IDs to backend to start the debate
    confirm({
      session_id: sessionId,
      debater_ids: debaters.map((d) => d.id),
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col gap-12 max-w-6xl mx-auto pb-24"
    >
      <div className="text-center md:text-left">
        <h1 className="text-4xl font-black leading-tight tracking-tight mb-2">
          {isZh ? "辩手选拔与组队" : "Agent Selection & Drafting"}
        </h1>
        <p className="text-slate-500 text-lg max-w-2xl">
          {isZh
            ? "查看主持人精选的辩手阵容，也可以用替补席上的候选人替换主力辩手。"
            : "Review selected specialists and swap with available substitutes for optimal cognitive diversity."}
        </p>
      </div>

      {/* Selected Lineup */}
      <section>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Users className="text-primary w-6 h-6" />
            <h2 className="text-2xl font-bold tracking-tight">
              {isZh ? "主力阵容" : "Selected Lineup"}
            </h2>
            <span className="ml-2 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-wider">
              {debaters.length} {isZh ? "位" : "Agents"}
            </span>
          </div>
        </div>

        <div className="flex gap-4 overflow-x-auto pb-6 snap-x">
          {debaters.map((agent) => (
            <div key={agent.id} className="flex-none w-64 snap-start group">
              <div className="relative bg-white border border-slate-200 rounded-2xl overflow-hidden transition-all hover:border-primary/50 hover:shadow-lg">
                <div className="aspect-[4/5] bg-slate-100 relative flex items-center justify-center">
                  <Avatar debater={agent} size="lg" className="w-full h-full !rounded-none" />
                  <span className="absolute top-3 right-3 text-3xl drop-shadow-md">{agent.avatar_emoji}</span>
                </div>
                <div className="p-4">
                  <h3 className="font-bold text-lg">{agent.name}</h3>
                  <p className="text-primary text-xs font-semibold uppercase tracking-wide mb-2">
                    {agent.stance}
                  </p>
                  <p
                    className="text-slate-500 text-sm leading-relaxed line-clamp-3"
                    title={agent.background}
                  >
                    {agent.background}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Substitutes */}
      {substituteDebaters.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-6 border-t border-slate-200 pt-10">
            <UserSearch className="text-primary w-6 h-6" />
            <h2 className="text-2xl font-bold tracking-tight">
              {isZh ? "候选替补" : "Available Substitutes"}
            </h2>
            <span className="ml-2 px-2.5 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-wider">
              {substituteDebaters.length} {isZh ? "位候选" : "Candidates"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {substituteDebaters.map((sub, subIdx) => (
              <div
                key={sub.id}
                className="flex items-start gap-4 p-4 bg-white border border-slate-200 rounded-xl group hover:border-primary/30 transition-all"
              >
                <Avatar debater={sub} size="md" className="!rounded-lg" />
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="font-bold">{sub.name}</h4>
                    <div className="relative">
                      <button
                        onClick={() => setOpenSwapIdx(openSwapIdx === subIdx ? null : subIdx)}
                        className="text-xs font-bold text-primary flex items-center gap-1 hover:underline cursor-pointer"
                      >
                        {isZh ? "替换" : "REPLACE"} <ArrowRightLeft className="w-3 h-3" />
                      </button>
                      {openSwapIdx === subIdx && (
                        <>
                          <div className="fixed inset-0 z-10" onClick={() => setOpenSwapIdx(null)} />
                          <div className="absolute right-0 top-full mt-2 bg-white border border-slate-200 shadow-xl rounded-lg p-2 z-20 w-48">
                            <p className="text-xs font-bold text-slate-500 mb-2">
                              {isZh ? "替换:" : "Swap with:"}
                            </p>
                            {debaters.map((sel, selIdx) => (
                              <button
                                key={sel.id}
                                onClick={() => {
                                  swapDebater(selIdx, subIdx);
                                  setOpenSwapIdx(null);
                                }}
                                className="w-full text-left px-2 py-1 text-sm hover:bg-primary/10 hover:text-primary rounded cursor-pointer"
                              >
                                {sel.name}
                              </button>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  <p className="text-[10px] font-bold text-primary/70 uppercase tracking-widest mb-1">
                    {sub.stance}
                  </p>
                  <p
                    className="text-slate-500 text-xs leading-relaxed line-clamp-2"
                    title={sub.background}
                  >
                    {sub.background}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Bottom bar */}
      <div className="fixed bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-bg via-bg/95 to-transparent flex justify-center items-end h-40 pointer-events-none z-20">
        <div className="max-w-6xl w-full flex flex-col md:flex-row items-center justify-between gap-6 pointer-events-auto">
          <div className="hidden md:block">
            <p className="text-slate-500 text-sm font-medium">
              {isZh ? "准备好进入辩论场了吗？" : "Ready to enter the arena?"}
            </p>
          </div>
          <button
            onClick={handleStart}
            disabled={confirming}
            className={`flex-1 md:flex-none px-12 h-14 rounded-xl text-white font-bold transition-all flex items-center justify-center gap-3 shadow-lg shadow-primary/20 ${
              confirming
                ? "bg-primary/50 cursor-not-allowed"
                : "bg-primary hover:opacity-90 cursor-pointer"
            }`}
          >
            {confirming
              ? (isZh ? "正在启动辩论…" : "Starting Debate…")
              : (isZh ? "确认阵容 & 开始辩论" : "Confirm & Start Debate")}
            <Rocket className="w-5 h-5" />
          </button>
        </div>
      </div>
    </motion.div>
  );
}
