from __future__ import annotations

import logging
import re
from typing import List, Tuple

from app.agents.context_manager import ContextManager
from app.models import DebaterConfig, DebateMessage, SearchResult
from app.providers.base import LLMProvider, SearchProvider

logger = logging.getLogger(__name__)


class DebaterAgent:
    def __init__(
        self,
        config: DebaterConfig,
        llm: LLMProvider,
        search: SearchProvider,
        context_manager: ContextManager | None = None,
    ) -> None:
        self.config = config
        self.llm = llm
        self.search = search
        self.context_manager = context_manager or ContextManager()
        self.rolling_summary = ""

    def _system_prompt(self) -> str:
        return (
            f"你是辩手 {self.config.name}。\n"
            f"背景：{self.config.background}\n"
            f"立场：{self.config.stance}\n"
            f"公共形象与表达偏好：{self.config.personality}\n"
            "你正在参与一场严肃的多方辩论，不是吵架节目。\n"
            "要求：\n"
            "1. 从立场、利益、激励、约束和后果出发辩论，而不是表演情绪。\n"
            "2. 可以尖锐，但不要进行人身攻击、贴标签、赌咒、喊口号或编造受贿阴谋。\n"
            "3. 尽量先指出一处你认可的边缘共识或对方有效担忧，再推进核心分歧。\n"
            "4. 每轮都要提供新的分析维度，例如成本、执行难度、制度约束、二阶影响、社会观察、历史类比或数据。\n"
            "5. 不要重复自己上一轮的原句；如果某点已经说过，就补充条件、证据或修正边界。\n"
            "6. 如果证据不足，要明确不确定性以及你愿意修正观点的条件。\n"
            "输出 180-260 字中文，信息密度高、专业、克制。"
        )

    async def produce_turn(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        enable_search: bool,
    ) -> Tuple[str, List[SearchResult]]:
        references: List[SearchResult] = []
        if enable_search:
            try:
                references = await self.search.search(f"{topic} {self.config.stance}", num_results=2)
            except Exception:
                references = []

        turn_instruction = (
            "请给出本轮发言。"
            "优先回应当前最值得澄清的一条异议，而不是机械反击最近一句。"
            "先给出一处有限共识或你认可的担忧，再说明核心分歧。"
            "必须引入新的理由、机制、事实、社会观察或可检验判断。"
            "不要复读，不要表演吵架。"
        )
        self.rolling_summary = self.context_manager.refresh_rolling_summary(messages)
        ctx = self.context_manager.build(
            current_speaker=self.config.name,
            system_prompt=self._system_prompt(),
            brief=brief,
            rolling_summary=self.rolling_summary,
            messages=messages,
            turn_instruction=turn_instruction,
        )

        refs_text = "\n".join([f"- {r.title}: {r.snippet[:120]}" for r in references])
        user_prompt = ctx.to_prompt()
        if refs_text:
            user_prompt = f"{user_prompt}\n\n## Optional Realtime References\n{refs_text}"

        try:
            text = await self.llm.chat(self._system_prompt(), user_prompt)
            if text.strip():
                return text.strip(), references
        except Exception as exc:
            logger.warning("Debater LLM failed for %s: %s", self.config.name, exc)

        return self._fallback_turn(topic, brief, messages, references), references

    def _fallback_turn(
        self,
        topic: str,
        brief: str,
        messages: List[DebateMessage],
        references: List[SearchResult],
    ) -> str:
        own_turn_index = sum(1 for msg in messages if msg.speaker == self.config.name)
        last_message = messages[-1] if messages else None
        style_lead = self._style_lead()
        stance_argument = self._stance_argument(topic, own_turn_index)
        counter = self._counter_line(last_message)
        evidence = self._evidence_line(brief, references, own_turn_index)
        close = self._close_line(topic, own_turn_index)
        return " ".join(part for part in [style_lead, counter, stance_argument, evidence, close] if part).strip()

    def _style_lead(self) -> str:
        style_map = {
            "high_signal": "先把结论摆在桌面上：",
            "structured": "我按条件、成本、后果三层来讲：",
            "blunt": "别把这事说成口号，先算账：",
            "narrative": "这件事最危险的地方在于：",
            "cross_exam": "我先追问一个绕不过去的问题：",
        }
        return style_map.get(self.config.speaking_style, "我的立场很明确：")

    def _stance_argument(self, topic: str, own_turn_index: int) -> str:
        stance = self.config.stance

        if any(word in stance for word in ["积极", "支持", "推进", "赞成"]):
            options = [
                "支持推进不等于无脑乐观，关键是证明收益大于副作用，而且执行链条清楚。",
                "我更看重行动带来的净增益，而不是停留在抽象价值判断里。",
                "如果一个方案连试错和纠偏空间都没有，就不该被叫做可推进方案。",
            ]
            return options[own_turn_index % len(options)]

        if any(word in stance for word in ["审慎", "监管", "风险", "反对", "怀疑"]):
            options = [
                "我会先问边界条件，因为没有边界的推进往往最后会反噬原目标。",
                "如果主要收益建立在乐观假设上，那审慎不是保守，而是基本理性。",
                "在风险分布高度不对称的时候，先降速比先冲刺更负责任。",
            ]
            return options[own_turn_index % len(options)]

        if any(word in stance for word in ["务实", "落地", "ROI", "成本", "商业"]):
            options = [
                "我关心的不是立场好不好听，而是资源、指标和落地成本能不能闭环。",
                "方案能否执行，取决于谁付成本、多久见效、失败后怎么止损。",
                "如果收益讲不清、成本算不明、责任链条也不完整，那就不是务实方案。",
            ]
            return options[own_turn_index % len(options)]

        options = [
            "这件事不能只看原则口号，必须把实际约束和外部性一起摆上来。",
            "我更在意决策有没有约束条件，而不是谁先把态度喊得更响。",
            "如果没有可验证判断，争论就只是在重复身份标签。",
        ]
        return options[own_turn_index % len(options)]

    def _counter_line(self, last_message: DebateMessage | None) -> str:
        if not last_message:
            return ""
        if last_message.speaker == self.config.name:
            return "我接着把上一轮没展开的点说透："

        stance = self.config.stance
        if any(word in stance for word in ["积极", "支持", "推进", "赞成"]):
            return f"回应 {last_message.speaker}：你刚才把风险讲得很满，但没有比较“不行动”的代价。"
        if any(word in stance for word in ["审慎", "监管", "风险", "反对", "怀疑"]):
            return f"回应 {last_message.speaker}：你强调立场没问题，但没有交代升级之后如何收场。"
        if any(word in stance for word in ["务实", "落地", "ROI", "成本", "商业"]):
            return f"回应 {last_message.speaker}：你说的是原则方向，可真正缺的是成本表、时间表和退出表。"
        return f"回应 {last_message.speaker}：你给出了判断，但支撑这个判断的约束条件还不够。"

    def _evidence_line(
        self,
        brief: str,
        references: List[SearchResult],
        own_turn_index: int,
    ) -> str:
        signals = self._brief_signals(brief, references)
        if not signals:
            return "主持人简报能提供的确定信息还不够多，所以越到后面越该追着证据和条件往下问。"
        return signals[own_turn_index % len(signals)]

    def _brief_signals(self, brief: str, references: List[SearchResult]) -> List[str]:
        bullet_lines = []
        for line in brief.splitlines():
            cleaned = re.sub(r"\s+", " ", line.strip("- ").strip())
            if cleaned and not cleaned.startswith("#"):
                bullet_lines.append(cleaned)
        fallback_points = [line for line in bullet_lines if len(line) > 20][:4]
        return [f"主持人简报里至少有一个值得继续追问的点：{line[:90]}。" for line in fallback_points]

    def _close_line(self, topic: str, own_turn_index: int) -> str:
        options = [
            "所以这轮我只认一件事：有没有可验证的判断和可执行的约束。",
            "如果这些条件答不出来，继续争论只会重复立场标签。",
            "真正像样的决策，不该靠重复人设推进。",
        ]
        return options[own_turn_index % len(options)]
