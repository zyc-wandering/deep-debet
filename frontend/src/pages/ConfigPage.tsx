import { useState } from "react";
import { useDebateStore } from "../store/debateStore";
import { DebateLanguage, DebateStartRequest } from "../types";

interface Props {
  onStart: (payload: DebateStartRequest) => void;
  isRunning: boolean;
}

const launchHighlights = [
  {
    label: "主持人先准备",
    value: "先调研后开辩",
    description: "主持人会先梳理背景与争点，再让辩手进入交锋。",
  },
  {
    label: "角色设计",
    value: "立场动机分离",
    description: "辩手会按机构位置、利益约束和分析框架拉开差异。",
  },
  {
    label: "实时交锋",
    value: "逐轮流式展开",
    description: "你可以直接看到论点生成过程，而不是只看最终整理稿。",
  },
] as const;

const systemFeatures = [
  {
    title: "结构化主持流程",
    description: "从调研、定调到开辩的过程连贯推进，不会在切换阶段时丢失上下文。",
  },
  {
    title: "更清晰的人设分化",
    description: "辩手通过利益驱动和分析方法产生分歧，而不是靠空洞的情绪化表演。",
  },
  {
    title: "更易读的总结输出",
    description: "报告会把核心主张、冲突点、证据与条件判断整合到同一个视图里。",
  },
  {
    title: "本地优先运行",
    description: "会话快照和总结报告都保留在本地工作区，便于回看和核对。",
  },
] as const;

export function ConfigPage({ onStart, isRunning }: Props) {
  const [topic, setTopic] = useState(
    "经济下行阶段，企业是否应该用裁员来优先控制成本？",
  );
  const [debateLanguage, setDebateLanguage] = useState<DebateLanguage>("zh");
  const [debaterCount, setDebaterCount] = useState(3);
  const [timeLimit, setTimeLimit] = useState(360);
  const [maxTurns, setMaxTurns] = useState(24);
  const [enableSearch, setEnableSearch] = useState(false);
  const [modelVariant, setModelVariant] = useState<DebateStartRequest["model_variant"]>("lite");
  const errorMessage = useDebateStore((s) => s.errorMessage);

  const minTurns = debaterCount * 3;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim() || isRunning) return;

    onStart({
      topic: topic.trim(),
      debater_count: debaterCount,
      time_limit_sec: timeLimit,
      max_turns: maxTurns,
      enable_debater_search: enableSearch,
      debate_language: debateLanguage,
      model_variant: modelVariant,
      fun_mode: "persona_clash",
    });
  };

  return (
    <div className="config-page">
      <header className="config-header">
        <div className="config-header-copy">
          <p className="eyebrow">DebateAI Room</p>
          <h1>真理越辩越明朗</h1>
          <h1>思维越深越广阔</h1>
          <p className="config-intro">
            先设定辩题、强度和时长。主持人会优先调研并确定讨论框架，再把辩手送上同一张
            辩论舞台，让整场流程比普通聊天记录更有层次。
          </p>
        </div>

        <div className="launch-strip" aria-label="会话亮点">
          {launchHighlights.map((item) => (
            <article key={item.label} className="launch-card">
              <span className="launch-label">{item.label}</span>
              <strong>{item.value}</strong>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </header>

      <form className="config-form" onSubmit={handleSubmit}>
        {errorMessage && <p className="error">{errorMessage}</p>}

        <div className="config-form-shell">
          <section className="config-form-main">
            <div className="form-section">
              <div className="section-kicker">
                <span className="section-index">01</span>
                <div>
                  <h2>定义这场辩论</h2>
                  <p>尽量使用存在真实权衡和现实压力的命题，这样主持人才能生成更有内容的分歧。</p>
                </div>
              </div>

              <label className="field">
                <span className="field-label">辩题</span>
                <textarea
                  className="topic-textarea"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="例如：AI 是否应该在高风险行业的内部政策起草中承担主要工作？"
                  minLength={5}
                  maxLength={240}
                  required
                  disabled={isRunning}
                />
              </label>
              <p className="field-hint">
                最适合的辩题通常带有现实压力、取舍冲突，而且不存在显而易见的安全答案。
              </p>

              <div className="language-panel" role="group" aria-label="辩论语言">
                <div className="language-panel-copy">
                  <span className="field-label">辩论过程语言</span>
                  <p className="field-hint">
                    只影响主持人调研、辩手发言、总结报告和追问内容的语言，不会改动界面文案。
                  </p>
                </div>

                <div className="language-toggle">
                  <button
                    type="button"
                    className={debateLanguage === "zh" ? "active" : ""}
                    onClick={() => setDebateLanguage("zh")}
                    disabled={isRunning}
                  >
                    中文辩论
                  </button>
                  <button
                    type="button"
                    className={debateLanguage === "en" ? "active" : ""}
                    onClick={() => setDebateLanguage("en")}
                    disabled={isRunning}
                  >
                    English Debate
                  </button>
                </div>
              </div>
            </div>

            <div className="form-section">
              <div className="section-kicker">
                <span className="section-index">02</span>
                <div>
                  <h2>调整运行参数</h2>
                  <p>在主持人正式开始前，先平衡辩手数量、时长预算和交锋轮次。</p>
                </div>
              </div>

              <div className="config-grid">
                <div className="form-field">
                  <label className="field-label">辩手数量</label>
                  <select
                    value={debaterCount}
                    onChange={(e) => setDebaterCount(Number(e.target.value))}
                    disabled={isRunning}
                  >
                    <option value={2}>2 位</option>
                    <option value={3}>3 位</option>
                    <option value={4}>4 位</option>
                    <option value={5}>5 位</option>
                  </select>
                </div>

                <div className="form-field">
                  <label className="field-label">时长上限</label>
                  <select
                    value={timeLimit}
                    onChange={(e) => setTimeLimit(Number(e.target.value))}
                    disabled={isRunning}
                  >
                    <option value={180}>3 分钟</option>
                    <option value={360}>6 分钟</option>
                    <option value={600}>10 分钟</option>
                    <option value={900}>15 分钟</option>
                  </select>
                </div>

                <div className="form-field">
                  <label className="field-label">最大轮次</label>
                  <select
                    value={maxTurns}
                    onChange={(e) => setMaxTurns(Number(e.target.value))}
                    disabled={isRunning}
                  >
                    <option value={12}>12 轮</option>
                    <option value={24}>24 轮</option>
                    <option value={36}>36 轮</option>
                    <option value={48}>48 轮</option>
                  </select>
                  <p className="field-hint">建议至少为 {minTurns} 轮。</p>
                </div>

                <div className="form-field">
                  <label className="field-label">模型档位</label>
                  <select
                    value={modelVariant}
                    onChange={(e) => setModelVariant(e.target.value as DebateStartRequest["model_variant"])}
                    disabled={isRunning}
                  >
                    <option value="lite">Lite</option>
                    <option value="pro">Pro</option>
                  </select>
                </div>
              </div>
            </div>

            <label className="toggle-field">
              <input
                type="checkbox"
                checked={enableSearch}
                onChange={(e) => setEnableSearch(e.target.checked)}
                disabled={isRunning}
              />
              <div>
                <span className="toggle-label">允许辩手实时联网检索</span>
                <span className="field-hint">
                  适合讨论时效性较强的话题，但会增加运行时长和外部 API 调用。
                </span>
              </div>
            </label>
          </section>

          <aside className="config-form-side">
            <div className="config-summary-card">
              <p className="eyebrow">启动摘要</p>

              <div className="summary-stat-grid">
                <article>
                  <span>辩手</span>
                  <strong>{debaterCount}</strong>
                </article>
                <article>
                  <span>时长</span>
                  <strong>{Math.floor(timeLimit / 60)} 分钟</strong>
                </article>
                <article>
                  <span>轮次</span>
                  <strong>{maxTurns}</strong>
                </article>
                <article>
                  <span>模型</span>
                  <strong>{modelVariant.toUpperCase()}</strong>
                </article>
                <article>
                  <span>语言</span>
                  <strong>{debateLanguage === "zh" ? "中文" : "English"}</strong>
                </article>
              </div>

              <div className="config-note">
                <span className="config-note-label">运行说明</span>
                <p>
                  计时会在辩手就位后才开始。前面的准备窗口会留给主持人完成调研、定调和组局。
                </p>
              </div>

              <div className="form-actions">
                <button
                  type="submit"
                  className="start-button"
                  disabled={isRunning || !topic.trim()}
                >
                  {isRunning ? "辩论进行中..." : "启动辩论室"}
                </button>
              </div>
            </div>
          </aside>
        </div>
      </form>

      <section className="config-features">
        <div className="section-kicker centered">
          <span className="section-index">03</span>
          <div>
            <h2>让整场辩论更像一套真正的工作台</h2>
            <p>每个界面都围绕同一种控制台语言来组织，而不是普通的应用外壳。</p>
          </div>
        </div>

        <div className="feature-grid">
          {systemFeatures.map((feature, index) => (
            <article key={feature.title} className="feature-card">
              <span className="feature-number">0{index + 1}</span>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
