import { useState } from "react";
import { Edit3, TrendingUp, Globe, Users, Repeat, PlayCircle, Cpu, Search } from "lucide-react";
import { DebateConfig } from "../types";

interface Props {
  onStart: (config: DebateConfig) => void;
}

const HOTSPOTS_ZH = [
  "AI 是否应该拥有法律人格？",
  "远程办公是否会成为未来主流？",
  "经济下行期企业应优先裁员还是降薪？",
  "人类是否应该加大深空探索投入？",
  "2026年全球经济环境下黄金走势与中东美伊战争的关系相关性研究",
];

const HOTSPOTS_EN = [
  "AI Ethics in Journalism",
  "The Future of Remote Work",
  "Space Exploration Funding",
  "Renewable Energy Policy",
];

const MAX_ROUNDS_LIMIT = 48;
const DEBATER_COUNT_OPTIONS = [2, 4, 6, 8] as const;

function getRoundBounds(numDebaters: number) {
  const minRounds = numDebaters * 3;
  const alignedMaxRounds =
    MAX_ROUNDS_LIMIT - ((MAX_ROUNDS_LIMIT - minRounds) % numDebaters);
  return { minRounds, alignedMaxRounds };
}

function snapRoundsToDebaterStep(value: number, numDebaters: number) {
  const { minRounds, alignedMaxRounds } = getRoundBounds(numDebaters);
  const clamped = Math.min(alignedMaxRounds, Math.max(minRounds, value));
  const snapped =
    minRounds + Math.round((clamped - minRounds) / numDebaters) * numDebaters;
  return Math.min(alignedMaxRounds, Math.max(minRounds, snapped));
}

export default function ConfigPhase({ onStart }: Props) {
  const [config, setConfig] = useState<DebateConfig>({
    topic: "",
    language: "zh",
    numDebaters: 4,
    maxRounds: 20,
    modelVariant: "lite",
    enableSearch: true,
  });

  const hotspots = config.language === "zh" ? HOTSPOTS_ZH : HOTSPOTS_EN;
  const wordCount = config.topic.split(/\s+/).filter(Boolean).length;
  const { minRounds, alignedMaxRounds } = getRoundBounds(config.numDebaters);

  return (
    <div className="relative flex flex-col gap-8 max-w-3xl mx-auto">
      {/* Hero background — grayscale, fading top-to-bottom */}
      <div
        className="pointer-events-none absolute -top-14 left-1/2 -translate-x-1/2 w-[min(1200px,140%)] aspect-[16/9] z-0 select-none"
        aria-hidden="true"
      >
        <img
          src="/background.jpeg"
          alt=""
          className="w-full h-full object-cover grayscale opacity-30"
          style={{
            maskImage:
              "linear-gradient(to bottom, black 5%, transparent 80%)",
            WebkitMaskImage:
              "linear-gradient(to bottom, black 5%, transparent 80%)",
          }}
          draggable={false}
        />
      </div>

      <div className="relative z-10 flex flex-col gap-3 text-center md:text-left">
        <h1 className="text-4xl font-black leading-tight tracking-tight">
          {config.language === "zh" ? "配置你的辩论" : "Configure Your Debate"}
        </h1>
        <p className="text-slate-600 text-lg">
          {config.language === "zh"
            ? "设定辩题和 AI 参数，开启一场多智能体深度讨论。"
            : "Define the topic and AI parameters for your multi-agent discussion."}
        </p>
      </div>

      <div className="relative z-10 bg-white/90 backdrop-blur-sm p-6 md:p-8 rounded-xl shadow-sm border border-primary/10 flex flex-col gap-8">
        {/* Topic */}
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Edit3 className="text-primary w-5 h-5" />
            <label className="text-lg font-semibold">
              {config.language === "zh" ? "辩论主题" : "Debate Topic"}
            </label>
          </div>
          <textarea
            className="w-full resize-none rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 border border-primary/20 bg-bg/50 p-4 text-base min-h-[160px]"
            placeholder={
              config.language === "zh"
                ? "例如：人工智能是否应该在未来十年内被赋予法律人格？（最多200字）"
                : "Example: Should AI be granted legal personhood in the next decade? (Up to 200 words)"
            }
            value={config.topic}
            onChange={(e) => setConfig({ ...config, topic: e.target.value })}
          />
          <div className="flex justify-end">
            <span className="text-xs text-slate-400">{wordCount} / 200 words</span>
          </div>

          {/* Hotspots */}
          <div className="flex flex-col gap-3 mt-2">
            <div className="flex items-center gap-2 text-slate-500">
              <TrendingUp className="w-4 h-4" />
              <span className="text-xs font-semibold uppercase tracking-wider">
                {config.language === "zh" ? "热门辩题推荐" : "Daily News Hotspots"}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {hotspots.map((spot) => (
                <button
                  key={spot}
                  onClick={() => setConfig({ ...config, topic: spot })}
                  className="px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium hover:bg-primary/20 hover:border-primary/40 transition-all"
                >
                  {spot}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Settings Grid */}
        <div className="bg-bg/50 rounded-xl p-5 border border-primary/5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Language */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Globe className="text-primary w-5 h-5" />
              <label className="text-base font-semibold">
                {config.language === "zh" ? "讨论语言" : "Discussion Language"}
              </label>
            </div>
            <div className="flex h-11 items-center justify-center rounded-lg bg-white p-1 border border-primary/10">
              {(["zh", "en"] as const).map((lang) => (
                <button
                  key={lang}
                  onClick={() => setConfig({ ...config, language: lang })}
                  className={`flex-1 h-full rounded-md text-sm font-medium transition-all ${
                    config.language === lang
                      ? "bg-primary text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-700 hover:bg-primary/5"
                  }`}
                >
                  {lang === "zh" ? "中文" : "English"}
                </button>
              ))}
            </div>
          </div>

          {/* Debater count */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Users className="text-primary w-5 h-5" />
              <label className="text-base font-semibold">
                {config.language === "zh" ? "辩手数量" : "Number of Debaters"}
              </label>
            </div>
            <div className="flex h-11 items-center justify-center rounded-lg bg-white p-1 border border-primary/10">
              {DEBATER_COUNT_OPTIONS.map((num) => (
                <button
                  key={num}
                  onClick={() => {
                    setConfig({
                      ...config,
                      numDebaters: num,
                      maxRounds: snapRoundsToDebaterStep(config.maxRounds, num),
                    });
                  }}
                  className={`flex-1 h-full rounded-md text-sm font-medium transition-all ${
                    config.numDebaters === num
                      ? "bg-primary text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-700 hover:bg-primary/5"
                  }`}
                >
                  {num}
                </button>
              ))}
            </div>
          </div>

          {/* Model variant */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Cpu className="text-primary w-5 h-5" />
              <label className="text-base font-semibold">
                {config.language === "zh" ? "模型档位" : "Model Variant"}
              </label>
            </div>
            <div className="flex h-11 items-center justify-center rounded-lg bg-white p-1 border border-primary/10">
              {(["lite", "pro"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setConfig({ ...config, modelVariant: v })}
                  className={`flex-1 h-full rounded-md text-sm font-medium transition-all ${
                    config.modelVariant === v
                      ? "bg-primary text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-700 hover:bg-primary/5"
                  }`}
                >
                  {v === "lite" ? "Lite" : "Pro"}
                </button>
              ))}
            </div>
          </div>

          {/* Enable search */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Search className="text-primary w-5 h-5" />
              <label className="text-base font-semibold">
                {config.language === "zh" ? "联网搜索" : "Web Search"}
              </label>
            </div>
            <div className="flex h-11 items-center justify-center rounded-lg bg-white p-1 border border-primary/10">
              {([false, true] as const).map((v) => (
                <button
                  key={String(v)}
                  onClick={() => setConfig({ ...config, enableSearch: v })}
                  className={`flex-1 h-full rounded-md text-sm font-medium transition-all ${
                    config.enableSearch === v
                      ? "bg-primary text-white shadow-sm"
                      : "text-slate-500 hover:text-slate-700 hover:bg-primary/5"
                  }`}
                >
                  {v
                    ? config.language === "zh" ? "开启" : "Enabled"
                    : config.language === "zh" ? "关闭" : "Disabled"}
                </button>
              ))}
            </div>
          </div>

          {/* Max rounds */}
          <div className="flex flex-col gap-3 md:col-span-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Repeat className="text-primary w-5 h-5" />
                <label className="text-base font-semibold">
                  {config.language === "zh" ? "最大轮次" : "Maximum Rounds"}
                </label>
              </div>
              <span className="text-sm font-bold text-primary px-2 py-1 bg-primary/10 rounded">
                {config.maxRounds} {config.language === "zh" ? "轮" : "Rounds"}
              </span>
            </div>
            <input
              type="range"
              min={minRounds}
              max={alignedMaxRounds}
              step={config.numDebaters}
              value={config.maxRounds}
              onChange={(e) =>
                setConfig({
                  ...config,
                  maxRounds: snapRoundsToDebaterStep(parseInt(e.target.value, 10), config.numDebaters),
                })
              }
            />
            <div className="flex justify-between text-xs text-slate-400">
              <span>Min: {minRounds}</span>
              <span>Step: {config.numDebaters}</span>
              <span>Max: {alignedMaxRounds}</span>
            </div>
          </div>
        </div>
        </div>

        {/* Start button */}
        <div className="pt-4">
          <button
            onClick={() => onStart(config)}
            disabled={!config.topic.trim()}
            className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 text-white font-bold text-lg h-14 rounded-xl shadow-[0_4px_16px_rgba(212,98,17,0.25)] transition-all active:scale-[0.98] disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
          >
            <PlayCircle className="w-6 h-6" />
            {config.language === "zh" ? "开始辩论" : "Start Debate"}
          </button>
        </div>
      </div>
    </div>
  );
}
