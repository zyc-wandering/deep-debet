from __future__ import annotations

import json
import logging
from typing import List, Tuple

from app.models import DebaterConfig, DebateMessage, SearchResult
from app.providers.base import LLMProvider, SearchProvider

logger = logging.getLogger(__name__)


HOST_SYSTEM_PROMPT = """You are a professional debate host and research analyst.
You produce balanced, evidence-oriented synthesis in concise Chinese.
"""


class HostAgent:
    def __init__(self, llm: LLMProvider, search: SearchProvider) -> None:
        self.llm = llm
        self.search = search

    async def research_topic(self, topic: str) -> Tuple[str, List[SearchResult]]:
        queries = [
            topic,
            f"{topic} 最新 争议",
            f"{topic} 数据 研究 报告",
        ]
        all_results: List[SearchResult] = []
        for q in queries:
            try:
                all_results.extend(await self.search.search(q, num_results=3))
            except Exception:
                continue

        if not all_results:
            return self._fallback_brief(topic), []

        citations_text = "\n".join(
            f"- {r.title}: {r.snippet[:160]} ({r.url})" for r in all_results[:9]
        )
        user_prompt = (
            f"话题：{topic}\n\n"
            f"请基于以下材料生成 500-800 字背景简报，要求中立、结构清晰。\n"
            f"材料：\n{citations_text}\n"
        )
        try:
            brief = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            if brief.strip():
                return brief.strip(), all_results
        except Exception as exc:
            logger.warning("Host research fallback activated for topic %r: %s", topic, exc)

        return self._fallback_brief(topic, all_results), all_results

    async def create_debaters(self, topic: str, debater_count: int, brief: str) -> List[DebaterConfig]:
        user_prompt = (
            f"针对话题《{topic}》，设计 {debater_count} 位辩手。\n"
            "请只返回 JSON 数组，字段: name, background, stance, personality, speaking_style, avatar_emoji。\n"
            "要求：\n"
            "1. 立场差异明显，但都必须像真实社会中的利益相关方或分析者，而不是网络骂战选手。\n"
            "2. 分歧要来自利益位置、风险偏好、制度约束、价值排序或分析框架，而不是单纯情绪对立。\n"
            "3. personality 和 speaking_style 要体现思考方式，例如数据派、制度派、产业派、人文派、交叉质询派；不要写成人身攻击、阴谋指控、脏话或表演型互怼。\n"
            "4. 每位辩手都应具备专业感，允许在边缘问题上承认对方合理之处，但在核心判断上保持鲜明分歧。\n"
            "5. speaking_style 请尽量使用短标签，例如 structured / empirical / blunt / narrative / cross_exam / high_signal。\n"
            f"背景简报：\n{brief[:1200]}"
        )
        try:
            raw = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            data = self._extract_json_array(raw)
            configs = [DebaterConfig(**row) for row in data[:debater_count]]
            if len(configs) >= debater_count:
                return configs[:debater_count]
        except Exception as exc:
            logger.warning("Host debater generation fallback activated for topic %r: %s", topic, exc)
        return self._fallback_debaters(topic, debater_count)

    async def summarize_debate(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        transcript = "\n".join([f"- {m.speaker}: {m.content}" for m in messages])
        refs = "\n".join([f"- [{r.title}]({r.url})" for r in references[:12]])
        user_prompt = (
            f"话题：{topic}\n\n"
            f"背景简报：\n{brief}\n\n"
            f"辩论记录：\n{transcript[:6000]}\n\n"
            "请输出 Markdown 报告，包含：\n"
            "1) 背景摘要\n2) 各方核心观点与代表发言\n3) 交锋焦点\n4) 综合分析\n5) 主持人结论\n"
            "语言简洁有信息密度。\n"
        )
        try:
            report = await self.llm.chat(HOST_SYSTEM_PROMPT, user_prompt)
            if report.strip():
                if refs:
                    report += f"\n\n## 参考链接\n{refs}\n"
                return report.strip()
        except Exception as exc:
            logger.warning("Host summary fallback activated for topic %r: %s", topic, exc)

        return self._fallback_report(topic, brief, messages, references)

    def _extract_json_array(self, raw: str) -> List[dict]:
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            # Prefer fenced body.
            body = parts[1] if len(parts) > 1 else text
            if body.strip().startswith("json"):
                body = body.strip()[4:]
            text = body.strip()
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("Expected list")
        return parsed

    def _fallback_brief(self, topic: str, results: List[SearchResult] | None = None) -> str:
        bullets = []
        for r in (results or [])[:6]:
            bullets.append(f"- {r.title}：{r.snippet[:120]}")
        if not bullets:
            bullets = [
                "- 该议题通常涉及技术可行性、伦理边界、商业激励和政策治理。",
                "- 需要区分短期影响与长期结构性影响，避免单一结论。",
                "- 建议关注利益相关方：普通用户、企业、监管者、研究者。",
            ]
        return (
            f"## {topic} 背景简报\n\n"
            "以下为主持人预备材料（MVP 回退版本）：\n"
            + "\n".join(bullets)
            + "\n\n本场辩论将围绕“价值、风险、可执行路径”展开。"
        )

    def _fallback_debaters(self, topic: str, debater_count: int) -> List[DebaterConfig]:
        pool = [
            DebaterConfig(
                name="技术极客 Lin",
                background="AI 系统架构师，偏工程理性",
                stance=f"对 {topic} 持积极推进态度",
                personality="快节奏、喜欢拿数据说话，偶尔毒舌",
                speaking_style="high_signal",
                avatar_emoji="🛠️",
            ),
            DebaterConfig(
                name="政策观察员 Zhou",
                background="公共政策研究者，关注制度设计",
                stance=f"对 {topic} 持审慎监管态度",
                personality="逻辑严谨、擅长追问边界条件",
                speaking_style="structured",
                avatar_emoji="🏛️",
            ),
            DebaterConfig(
                name="商业操盘手 Chen",
                background="互联网产品负责人，关注增长和 ROI",
                stance=f"对 {topic} 持务实落地态度",
                personality="结果导向、善于算账、吐槽直接",
                speaking_style="blunt",
                avatar_emoji="📈",
            ),
            DebaterConfig(
                name="人文批评者 Fang",
                background="社会学作者，长期观察技术与人",
                stance=f"对 {topic} 强调社会与伦理风险",
                personality="语言锋利但不失温度",
                speaking_style="narrative",
                avatar_emoji="📚",
            ),
            DebaterConfig(
                name="怀疑主义者 Xu",
                background="独立评论人，专挑假设漏洞",
                stance=f"对 {topic} 持怀疑和反直觉立场",
                personality="爱抬杠、抓概念漏洞",
                speaking_style="cross_exam",
                avatar_emoji="🧪",
            ),
        ]
        return pool[:debater_count]

    def _fallback_report(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        by_speaker: dict[str, list[str]] = {}
        for msg in messages:
            by_speaker.setdefault(msg.speaker, []).append(msg.content)

        lines = [
            f"# 辩论报告：{topic}",
            "",
            "## 背景摘要",
            brief,
            "",
            "## 各方核心观点",
        ]
        for speaker, quotes in by_speaker.items():
            lines.append(f"### {speaker}")
            lines.append(f"- 代表观点：{quotes[0] if quotes else '无'}")
            lines.append(f"- 发言次数：{len(quotes)}")
            lines.append("")

        lines.extend(["## 主持人结论", "该议题不存在单一正确答案，建议按场景分层决策。", ""])
        if references:
            lines.append("## 参考链接")
            for r in references[:12]:
                lines.append(f"- [{r.title}]({r.url})")
        return "\n".join(lines).strip()
