import { useState, useRef, useEffect } from "react";
import {
  Download,
  FileText,
  Share2,
  BrainCircuit,
  Gavel,
  CheckCircle2,
  MessageSquare,
  Send,
  Trophy,
  Swords,
} from "lucide-react";
import { motion } from "motion/react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useDebateStore } from "../store/debateStore";
import { useFollowUp } from "../hooks/useFollowUp";
import Avatar from "./Avatar";
import { generateTranscriptMarkdown } from "../utils/generateTranscriptMarkdown";

/**
 * Safely extract a readable string from an unknown value.
 * Walks known field names to avoid rendering [object Object].
 */
function extractText(val: unknown, keys: string[] = ["text", "point", "content", "argument", "name"]): string {
  if (val == null) return "";
  if (typeof val === "string") return val;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  if (Array.isArray(val)) return val.map((v) => extractText(v, keys)).join("; ");
  if (typeof val === "object") {
    const obj = val as Record<string, unknown>;
    for (const k of keys) {
      if (obj[k] && typeof obj[k] === "string") return obj[k] as string;
    }
    // Last resort: join all string values
    const parts = Object.values(obj)
      .filter((v) => typeof v === "string" && v.length > 0)
      .map(String);
    if (parts.length > 0) return parts.join(" — ");
  }
  return "";
}

interface ParsedConclusion {
  winning_argument?: string;
  strongest_debater?: string;
  reasoning?: string;
  reasoning_list?: string[];
  text?: string;
}

function parseObjectConclusion(obj: Record<string, unknown>): ParsedConclusion {
  return {
    winning_argument: typeof obj.winning_argument === "string" ? obj.winning_argument : undefined,
    strongest_debater: typeof obj.strongest_debater === "string" ? obj.strongest_debater : undefined,
    reasoning: typeof obj.reasoning === "string" ? obj.reasoning : undefined,
    reasoning_list: Array.isArray(obj.reasoning_list)
      ? obj.reasoning_list.map((r) => extractText(r))
      : undefined,
  };
}

/**
 * Strip markdown code fences from a string.
 * Handles ```json\n...\n``` and ```\n...\n``` patterns.
 */
function stripCodeFences(s: string): string {
  let cleaned = s.trim();
  if (cleaned.startsWith("```")) {
    // Remove opening fence line (```json, ```typescript, or plain ```)
    const firstNewline = cleaned.indexOf("\n");
    cleaned = firstNewline >= 0 ? cleaned.slice(firstNewline + 1) : cleaned.slice(3);
  }
  if (cleaned.endsWith("```")) {
    cleaned = cleaned.slice(0, -3).trimEnd();
  }
  return cleaned;
}

/**
 * Try to parse a string as JSON, stripping code fences if needed.
 */
function tryParseJson(s: string): Record<string, unknown> | null {
  // Try raw first
  for (const candidate of [s.trim(), stripCodeFences(s)]) {
    try {
      const parsed = JSON.parse(candidate);
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
        return parsed;
      }
    } catch { /* continue */ }
  }
  return null;
}

/**
 * Parse host_conclusion which can be:
 * - a plain markdown string
 * - a JSON-stringified object (possibly wrapped in markdown code fences)
 * - or a proper JS object { winning_argument, strongest_debater, reasoning, reasoning_list }
 */
function parseConclusion(raw: unknown): ParsedConclusion {
  if (!raw) return {};

  // String: could be markdown, JSON, or JSON wrapped in code fences
  if (typeof raw === "string") {
    const parsed = tryParseJson(raw);
    if (parsed && ("winning_argument" in parsed || "strongest_debater" in parsed)) {
      return parseObjectConclusion(parsed);
    }
    return { text: raw.trim() };
  }

  // Object: extract known fields
  if (typeof raw === "object" && raw !== null) {
    return parseObjectConclusion(raw as Record<string, unknown>);
  }

  return { text: String(raw) };
}

export default function SummaryPhase() {
  const topic = useDebateStore((s) => s.topic);
  const hostSummary = useDebateStore((s) => s.hostSummary);
  const reportMarkdown = useDebateStore((s) => s.reportMarkdown);
  const structuredReport = useDebateStore((s) => s.structuredReport);
  const debaters = useDebateStore((s) => s.debaters);
  const substituteDebaters = useDebateStore((s) => s.substituteDebaters);
  const allDebaters = [...debaters, ...substituteDebaters];
  const transcript = useDebateStore((s) => s.transcript);
  const stageLines = useDebateStore((s) => s.stageLines);
  const sessionId = useDebateStore((s) => s.sessionId);
  const followUpMessages = useDebateStore((s) => s.followUpMessages);
  const isFollowUpStreaming = useDebateStore((s) => s.isFollowUpStreaming);
  const debateLanguage = useDebateStore((s) => s.debateLanguage);
  const status = useDebateStore((s) => s.status);
  const reset = useDebateStore((s) => s.reset);

  const { submitFollowUp } = useFollowUp();
  const [chatInput, setChatInput] = useState("");
  const [chatTarget, setChatTarget] = useState("host");
  const chatRef = useRef<HTMLDivElement>(null);
  const isZh = debateLanguage === "zh";

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [followUpMessages]);

  const handleDownload = () => {
    const content = reportMarkdown || hostSummary || "";
    if (!content) return;
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `debate-summary-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadTranscript = () => {
    if (transcript.length === 0) return;
    const md = generateTranscriptMarkdown({
      topic,
      debaters,
      stageLines,
      transcript,
      isZh,
    });
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `debate-transcript-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleChat = () => {
    if (!chatInput.trim() || isFollowUpStreaming || !sessionId) return;
    submitFollowUp({
      session_id: sessionId,
      target_role: chatTarget,
      question: chatInput.trim(),
    });
    setChatInput("");
  };

  const isStreaming = status === "running" && !reportMarkdown;
  const conclusion = structuredReport
    ? parseConclusion(structuredReport.host_conclusion)
    : null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col gap-6 max-w-5xl mx-auto pb-10"
    >
      {/* Header bar */}
      <div className="flex flex-wrap justify-between items-center bg-white p-4 rounded-xl shadow-sm border border-primary/10 gap-3">
        <h2 className="text-xl font-bold">{isZh ? "辩论分析" : "Debate Intelligence"}</h2>
        <div className="flex gap-3">
          <button
            onClick={handleDownloadTranscript}
            disabled={transcript.length === 0}
            className="flex items-center gap-2 bg-primary/10 text-primary px-4 py-2 rounded-lg text-sm font-bold hover:bg-primary/20 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <FileText className="w-4 h-4" />
            {isZh ? "下载辩论记录" : "Download Transcript"}
          </button>
          <button
            onClick={handleDownload}
            disabled={!reportMarkdown && !hostSummary}
            className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-primary/90 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <Download className="w-4 h-4" />
            {isZh ? "下载报告" : "Download Report"}
          </button>
          <button
            onClick={reset}
            className="flex items-center gap-2 bg-primary/10 text-primary px-4 py-2 rounded-lg text-sm font-bold hover:bg-primary/20 transition-colors cursor-pointer"
          >
            <Share2 className="w-4 h-4" />
            {isZh ? "新辩论" : "New Debate"}
          </button>
        </div>
      </div>

      {/* Hero */}
      <div className="bg-gradient-to-b from-[#221810]/80 to-[#221810] rounded-xl p-8 text-white shadow-lg relative overflow-hidden">
        <div className="relative z-10">
          <span className="bg-primary px-3 py-1 rounded text-[10px] uppercase font-bold mb-4 inline-block">
            {isZh ? "辩论结束" : "Post-Game Phase"}
          </span>
          <h1 className="text-3xl md:text-4xl font-bold leading-tight mb-2">
            {isZh ? "辩论总结：" : "Debate Concluded: "}
            {topic}
          </h1>
          <p className="text-slate-300 max-w-2xl">
            {isZh
              ? "以下是本场辩论的全面分析与结论。"
              : "Final assessment and comprehensive summary."}
          </p>
        </div>
      </div>

      {/* Content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main content */}
        <div className="lg:col-span-2 flex flex-col gap-6">

          {/* ── Verdict Card (from structuredReport.host_conclusion) ── */}
          {conclusion && (conclusion.winning_argument || conclusion.strongest_debater || conclusion.reasoning || conclusion.reasoning_list?.length || conclusion.text) && (
            <section className="bg-gradient-to-br from-[#221810] to-[#1a1209] text-white rounded-xl shadow-lg border border-primary/20 overflow-hidden">
              <div className="flex items-center gap-3 px-6 pt-6 pb-4">
                <Trophy className="text-amber-400 w-6 h-6" />
                <h2 className="text-xl font-bold">
                  {isZh ? "裁决结果" : "Final Verdict"}
                </h2>
              </div>

              {conclusion.text ? (
                <div className="px-6 pb-6 text-slate-200 leading-relaxed prose prose-invert max-w-none prose-p:text-slate-200 prose-strong:text-white">
                  <Markdown remarkPlugins={[remarkGfm]}>{conclusion.text}</Markdown>
                </div>
              ) : (
                <div className="flex flex-col">
                  {/* Winning argument + strongest debater: hero row */}
                  {(conclusion.winning_argument || conclusion.strongest_debater) && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-white/5">
                      {conclusion.winning_argument && (
                        <div className="bg-[#1a1209] p-5 flex flex-col gap-2">
                          <div className="flex items-center gap-2">
                            <Swords className="text-primary w-4 h-4 shrink-0" />
                            <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                              {isZh ? "胜出论点" : "Winning Argument"}
                            </span>
                          </div>
                          <p className="text-slate-100 font-medium text-sm leading-relaxed">
                            {conclusion.winning_argument}
                          </p>
                        </div>
                      )}
                      {conclusion.strongest_debater && (
                        <div className="bg-[#1a1209] p-5 flex flex-col gap-2">
                          <div className="flex items-center gap-2">
                            <Trophy className="text-amber-400 w-4 h-4 shrink-0" />
                            <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                              {isZh ? "最强辩手" : "Strongest Debater"}
                            </span>
                          </div>
                          <p className="text-amber-300 font-bold text-lg">
                            {conclusion.strongest_debater}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Reasoning summary */}
                  {conclusion.reasoning && (
                    <div className="mx-6 mt-4 p-4 bg-white/5 rounded-lg border border-white/10">
                      <p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-1.5">
                        {isZh ? "裁决依据" : "Verdict Basis"}
                      </p>
                      <p className="text-sm text-slate-300 leading-relaxed">{conclusion.reasoning}</p>
                    </div>
                  )}

                  {/* Reasoning list */}
                  {conclusion.reasoning_list && conclusion.reasoning_list.length > 0 && (
                    <div className="px-6 py-4">
                      <p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-3">
                        {isZh ? "胜出理由" : "Reasons for Victory"}
                      </p>
                      <ul className="space-y-2.5">
                        {conclusion.reasoning_list.map((r, i) => (
                          <li key={i} className="flex items-start gap-3 text-sm text-slate-300">
                            <span className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                              {i + 1}
                            </span>
                            <span className="leading-relaxed">{r}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}

          {/* ── Full Report (reportMarkdown = 600-800 word full report) ── */}
          {reportMarkdown ? (
            <section className="bg-white p-8 rounded-xl border border-primary/10 shadow-sm">
              <div className="flex items-center gap-3 mb-6">
                <BrainCircuit className="text-primary w-6 h-6" />
                <h2 className="text-2xl font-bold">
                  {isZh ? "完整报告" : "Full Report"}
                </h2>
              </div>
              <div className="prose prose-slate max-w-none prose-headings:text-slate-800 prose-p:text-slate-600 prose-strong:text-slate-800 prose-li:text-slate-600">
                <Markdown remarkPlugins={[remarkGfm]}>{reportMarkdown}</Markdown>
              </div>
            </section>
          ) : hostSummary ? (
            /* Streaming summary — show what we have so far */
            <section className="bg-white p-8 rounded-xl border border-primary/10 shadow-sm">
              <div className="flex items-center gap-3 mb-6">
                <BrainCircuit className="text-primary w-6 h-6" />
                <h2 className="text-2xl font-bold">
                  {isZh ? "主持人总结" : "Host Summary"}
                </h2>
              </div>
              <div className="prose prose-slate max-w-none">
                <Markdown remarkPlugins={[remarkGfm]}>{hostSummary}</Markdown>
              </div>
              {isStreaming && (
                <div className="mt-4 flex items-center gap-2 text-primary">
                  <div className="w-2 h-2 bg-primary rounded-full animate-pulse" />
                  <span className="text-sm font-medium">
                    {isZh ? "正在生成..." : "Generating..."}
                  </span>
                </div>
              )}
            </section>
          ) : (
            <div className="bg-white p-12 rounded-xl border border-primary/10 shadow-sm flex flex-col items-center justify-center gap-4">
              <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
              <p className="text-slate-500 font-medium">
                {isZh ? "正在生成辩论总结..." : "Generating debate summary..."}
              </p>
            </div>
          )}

          {/* ── Structured breakdown (supplementary sections) ── */}
          {structuredReport && (structuredReport.core_arguments?.length > 0 || structuredReport.clash_points?.length > 0) && (
            <section className="bg-white p-8 rounded-xl border border-primary/10 shadow-sm flex flex-col gap-8">
              {/* Core arguments */}
              {structuredReport.core_arguments?.length > 0 && (
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <Gavel className="text-primary w-6 h-6" />
                    <h2 className="text-2xl font-bold">
                      {isZh ? "各方核心论点" : "Core Arguments"}
                    </h2>
                  </div>
                  <ul className="space-y-4">
                    {structuredReport.core_arguments.map((arg, idx) => (
                      <li
                        key={idx}
                        className="flex gap-4 p-4 bg-primary/5 rounded-lg border-l-4 border-primary"
                      >
                        <span className="font-bold text-primary shrink-0">
                          {String(idx + 1).padStart(2, "0")}
                        </span>
                        <div>
                          <p className="font-bold text-sm mb-1">
                            {arg.speaker} — {arg.stance}
                          </p>
                          <ul className="text-slate-700 text-sm space-y-1">
                            {arg.key_points.map((pt, i) => {
                              const text = extractText(pt, ["point", "text", "content", "argument"]);
                              return text ? (
                                <li key={i} className="italic">
                                  &ldquo;{text}&rdquo;
                                </li>
                              ) : null;
                            })}
                          </ul>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Clash points */}
              {structuredReport.clash_points?.length > 0 && (
                <div className="border-t border-primary/5 pt-8">
                  <div className="flex items-center gap-3 mb-4">
                    <Swords className="text-primary w-6 h-6" />
                    <h2 className="text-2xl font-bold">
                      {isZh ? "争议焦点" : "Clash Points"}
                    </h2>
                  </div>
                  <div className="space-y-4">
                    {structuredReport.clash_points.map((cp, idx) => (
                      <div key={idx} className="p-4 bg-amber-50/50 rounded-lg border border-amber-200/50">
                        <h4 className="font-bold text-sm text-primary mb-2">
                          {extractText(cp.topic, ["text", "name", "topic", "title"])}
                        </h4>
                        <div className="space-y-2">
                          {Object.entries(cp.positions).map(([debater, pos]) => (
                            <div key={debater} className="text-sm text-slate-600">
                              <span className="font-semibold text-slate-800">{debater}：</span>
                              {extractText(pos, ["argument", "point", "text", "content", "position"])}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {/* ── Follow-up Q&A ── */}
          {status === "done" && (
            <section className="bg-white p-8 rounded-xl border border-primary/10 shadow-sm">
              <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                <MessageSquare className="text-primary w-6 h-6" />
                {isZh ? "辩后追问" : "Post-Debate Follow-up"}
              </h3>

              {/* Target selector */}
              <div className="flex flex-wrap gap-2 mb-4">
                <button
                  onClick={() => setChatTarget("host")}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                    chatTarget === "host"
                      ? "bg-primary text-white"
                      : "bg-primary/10 text-primary hover:bg-primary/20"
                  }`}
                >
                  {isZh ? "主持人" : "Host"}
                </button>
                {allDebaters.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setChatTarget(d.name)}
                    className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                      chatTarget === d.name
                        ? "bg-primary text-white"
                        : "bg-primary/10 text-primary hover:bg-primary/20"
                    }`}
                  >
                    {d.avatar_emoji} {d.name}
                  </button>
                ))}
              </div>

              {/* Chat history */}
              {followUpMessages.length > 0 && (
                <div
                  ref={chatRef}
                  className="flex flex-col gap-4 mb-4 max-h-64 overflow-y-auto p-4 bg-slate-50 rounded-lg"
                >
                  {followUpMessages.map((msg) => (
                    <div key={msg.id} className="flex flex-col gap-2">
                      <div className="flex flex-col items-end">
                        <span className="text-[10px] text-slate-400 mb-1 uppercase font-bold">
                          {isZh ? "你" : "You"} → {msg.target_role}
                        </span>
                        <div className="p-3 rounded-xl max-w-[80%] bg-primary text-white text-sm">
                          {msg.question}
                        </div>
                      </div>
                      {(msg.response || msg.isStreaming) && (
                        <div className="flex flex-col items-start">
                          <span className="text-[10px] text-slate-400 mb-1 uppercase font-bold">
                            {msg.target_role}
                          </span>
                          <div className="p-3 rounded-xl max-w-[80%] bg-bg border border-primary/10 text-slate-700 text-sm">
                            {msg.response ? (
                              <Markdown remarkPlugins={[remarkGfm]}>{msg.response}</Markdown>
                            ) : (
                              <div className="flex gap-1">
                                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" />
                                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0.1s" }} />
                                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0.2s" }} />
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Input */}
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleChat();
                  }
                }}
                className="min-h-[80px] w-full p-4 rounded-lg bg-bg border border-primary/10 text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none transition-shadow"
                placeholder={
                  isZh
                    ? `向${chatTarget === "host" ? "主持人" : chatTarget}提问...`
                    : `Ask ${chatTarget} a follow-up question...`
                }
              />
              <div className="flex justify-between items-center mt-3">
                <p className="text-xs text-slate-500">
                  {isZh ? "按 Enter 发送，Shift+Enter 换行" : "Enter to send, Shift+Enter for new line"}
                </p>
                <button
                  onClick={handleChat}
                  disabled={isFollowUpStreaming || !chatInput.trim()}
                  className="bg-primary text-white px-6 py-2 rounded-lg font-bold hover:bg-primary/90 transition-colors flex items-center gap-2 disabled:opacity-50 cursor-pointer"
                >
                  <span>{isZh ? "发送" : "Send"}</span>
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </section>
          )}
        </div>

        {/* Sidebar */}
        <div className="flex flex-col gap-6">
          {/* Participating agents */}
          <aside className="bg-white p-6 rounded-xl border border-primary/10 shadow-sm">
            <h3 className="text-lg font-bold mb-4">
              {isZh ? "参与辩手" : "Participating Agents"}
            </h3>
            <div className="flex flex-col gap-4">
              {allDebaters.map((agent) => (
                <div
                  key={agent.id}
                  className="flex flex-col p-4 bg-primary/5 rounded-lg border border-primary/10"
                >
                  <div className="flex items-center gap-3 mb-2">
                    <Avatar debater={agent} size="sm" />
                    <div>
                      <p className="font-bold text-sm">{agent.name}</p>
                      <p className="text-xs text-primary">{agent.stance}</p>
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-2">{agent.background}</p>
                </div>
              ))}
            </div>
          </aside>

          {/* Debate metrics */}
          <div className="bg-white p-6 rounded-xl border border-primary/10 shadow-sm">
            <h4 className="font-bold mb-4 flex items-center gap-2 text-slate-900">
              <BrainCircuit className="w-5 h-5 text-primary" />
              {isZh ? "辩论数据" : "Debate Metrics"}
            </h4>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-primary/5 p-3 rounded-lg">
                <p className="text-xs text-primary font-medium">{isZh ? "发言轮次" : "Turns"}</p>
                <p className="text-2xl font-bold text-slate-900">{transcript.length}</p>
              </div>
              <div className="bg-primary/5 p-3 rounded-lg">
                <p className="text-xs text-primary font-medium">{isZh ? "辩手数" : "Agents"}</p>
                <p className="text-2xl font-bold text-slate-900">{allDebaters.length}</p>
              </div>
              {structuredReport?.clash_points && (
                <div className="bg-primary/5 p-3 rounded-lg col-span-2">
                  <p className="text-xs text-primary font-medium">{isZh ? "争议焦点" : "Clash Points"}</p>
                  <p className="text-2xl font-bold text-slate-900">{structuredReport.clash_points.length}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
