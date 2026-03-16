from __future__ import annotations

import logging
from typing import Optional
from pathlib import Path
import httpx
import uuid

from app.config import settings

logger = logging.getLogger(__name__)


class ImageGenerationProvider:
    """Provider for generating images using ByteDance Seedream via Ark API."""

    # Model: doubao-seedream-5-0-260128
    DEFAULT_MODEL = "doubao-seedream-5-0-260128"
    DEFAULT_SIZE = "2048x2048"
    AVATAR_SIZE = "1920x1920"
    LANDSCAPE_SIZE = "2560x1440"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.ark_api_key or settings.openai_api_key
        self.model = model or self.DEFAULT_MODEL
        self.enabled = bool(self.api_key and "ark.cn-beijing.volces.com" in self.base_url)

    async def generate_image(
        self,
        prompt: str,
        size: str = DEFAULT_SIZE,
        watermark: bool = True,
    ) -> Optional[str]:
        """Generate an image and return the URL.

        Args:
            prompt: The image generation prompt
            size: Image size (default: 2K)
            watermark: Whether to add watermark (default: True)

        Returns:
            URL of the generated image, or None if generation failed
        """
        if not self.enabled:
            logger.warning("Image generation not enabled: ARK_API_KEY not configured or wrong base URL")
            return None

        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "response_format": "url",
        }

        if watermark:
            # OpenAI SDK uses extra_body for additional parameters
            payload["extra_body"] = {"watermark": True}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/images/generations"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

                if data.get("data") and len(data["data"]) > 0:
                    image_url = data["data"][0].get("url")
                    logger.info(f"Image generated successfully: {image_url[:50]}...")
                    return image_url
                else:
                    logger.error(f"No image data in response: {data}")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(f"Image generation HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return None

    async def download_image(self, image_url: str, output_path: Path) -> bool:
        """Download an image from URL to local path.

        Args:
            image_url: URL of the image to download
            output_path: Local path to save the image

        Returns:
            True if download succeeded, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(image_url)
                response.raise_for_status()

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)
                logger.info(f"Image downloaded to: {output_path}")
                return True

        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            return False


class ImageGenerationService:
    """High-level service for debate-related image generation."""

    def __init__(self) -> None:
        self.provider = ImageGenerationProvider()

    def _get_images_dir(self, debate_dir: str | Path | None) -> Path:
        """Get images directory, either from debate_dir or fallback."""
        if debate_dir:
            images_dir = Path(debate_dir) / "images"
        else:
            images_dir = settings.data_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        return images_dir

    @staticmethod
    def _to_relative_path(output_path: Path) -> str:
        """Convert absolute image path to a path relative to debates_dir.

        This relative path is used by the frontend to request images
        via /api/images/{relative_path}.
        """
        try:
            return str(output_path.relative_to(settings.debates_dir)).replace("\\", "/")
        except ValueError:
            # Fallback: just return absolute path
            return str(output_path)

    def _generate_avatar_prompt(self, debater: dict) -> str:
        """Generate a prompt for debater avatar."""
        name = debater.get("name", "辩手")
        age = debater.get("age", "年龄未说明")
        ethnicity = debater.get("ethnicity", "人种/族裔未说明")
        background = debater.get("background", "专业人士")
        personality = debater.get("personality", "理性")
        stance = debater.get("stance", "中立")
        avatar_emoji = debater.get("avatar_emoji", "🎙️")

        # Create a vivid character description
        prompt = f"""创建一个专业的辩论选手头像，采用现代写实风格的高品质数字肖像。

角色特征:
- 姓名: {name}
- 年龄: {age}
- 人种/族裔: {ethnicity}
- 身份: {background}
- 性格: {personality}
- 立场: {stance}
- 代表符号: {avatar_emoji}

艺术风格:
- 现代写实风格，高品质数字肖像，真实但不过度照片感
- 半身像，正面或约30度侧面角度，主体清晰居中
- 人物表情专注、克制、像在认真思考和审视问题
- 穿着避免千篇一律的西装革履，应符合人物身份、职业、年龄与气质
- 根据角色背景自然加入细节: 帽子、眼镜、胡须、发型、皮肤纹理、年龄痕迹、文化饰品等
- 人种、年龄、职业特征要有辨识度，但呈现应自然、尊重、不刻板
- 配色专业稳重，带有微妙层次和真实材质表现
- 背景简洁虚化或柔和环境衬底，不喧宾夺主
- 整体氛围: 智慧、理性、专业、有真实人物感
- 光影柔和细腻，面部结构、肤质与小细节清楚可见
- 避免模板化、避免所有角色看起来像同一种商务人像
"""
        return prompt.strip()

    def _generate_background_prompt(self, topic: str, debaters: list) -> str:
        """Generate a prompt for debate stage background."""
        debater_names = ", ".join([d.get("name", "辩手") for d in debaters[:3]])

        prompt = f"""创建一个高端辩论赛场的背景图。

辩论主题: {topic}
参与辩手: {debater_names}

场景描述:
- 现代化辩论厅或高端会议室
- 正式而充满智慧交锋的氛围
- 舞台中央有演讲台或辩论桌
- 背景有巨大的LED屏幕显示主题
- 聚光灯效果，营造紧张感

艺术风格:
- 电影级光影效果，暗调风格
- 蓝紫色渐变与暖金色点缀
- 科技感与学术氛围结合
- 深景深效果，前景清晰背景虚化
- 8K画质，超精细渲染
- 氛围: 严肃、智慧、紧张、专业
"""
        return prompt.strip()

    def _generate_summary_prompt(self, topic: str, host_name: str = "主持人", debaters: list = None) -> str:
        """Generate a prompt for debate summary image."""
        debater_names = ", ".join([d.get("name", "辩手") for d in (debaters or [])[:4]])

        prompt = f"""创建一张辩论总结海报。

辩论主题: {topic}
主持人: {host_name}
参与辩手: {debater_names}

构图描述:
- 主持人站在中央，手持总结报告
- 两侧是各位辩手的剪影或半身像
- 背景是辩论主题相关的视觉元素
- 整体像电影海报或纪录片封面

艺术风格:
- 电影海报级构图
- 戏剧性光影，主光源从上方照射
- 深色调配合金色/橙色强调光
- 文字区域留白（不需要真的文字）
- 史诗感与学术感的结合
- 高品质渲染，细节丰富
- 氛围: 总结、洞见、思想碰撞后的升华
"""
        return prompt.strip()

    async def generate_debater_avatar(
        self, debater: dict, session_id: str, debate_dir: str | Path | None = None,
    ) -> Optional[str]:
        """Generate avatar for a debater.

        Returns:
            Local path to the generated image, or None if failed
        """
        prompt = self._generate_avatar_prompt(debater)
        image_url = await self.provider.generate_image(prompt, size=ImageGenerationProvider.AVATAR_SIZE)

        if not image_url:
            return None

        images_dir = self._get_images_dir(debate_dir)
        safe_name = debater.get("name", "unknown").replace(" ", "_")
        filename = f"avatar_{safe_name}_{uuid.uuid4().hex[:8]}.png"
        output_path = images_dir / filename

        if await self.provider.download_image(image_url, output_path):
            return self._to_relative_path(output_path)
        return None

    async def generate_debate_background(
        self, topic: str, debaters: list, session_id: str, debate_dir: str | Path | None = None,
    ) -> Optional[str]:
        """Generate background for debate stage.

        Returns:
            Local path to the generated image, or None if failed
        """
        prompt = self._generate_background_prompt(topic, debaters)
        image_url = await self.provider.generate_image(prompt, size=ImageGenerationProvider.LANDSCAPE_SIZE)

        if not image_url:
            return None

        images_dir = self._get_images_dir(debate_dir)
        filename = f"bg_{uuid.uuid4().hex[:8]}.png"
        output_path = images_dir / filename

        if await self.provider.download_image(image_url, output_path):
            return self._to_relative_path(output_path)
        return None

    async def generate_summary_image(
        self, topic: str, debaters: list, session_id: str, debate_dir: str | Path | None = None,
    ) -> Optional[str]:
        """Generate summary image for the debate.

        Returns:
            Local path to the generated image, or None if failed
        """
        prompt = self._generate_summary_prompt(topic, debaters=debaters)
        image_url = await self.provider.generate_image(prompt, size=ImageGenerationProvider.LANDSCAPE_SIZE)

        if not image_url:
            return None

        images_dir = self._get_images_dir(debate_dir)
        filename = f"summary_{uuid.uuid4().hex[:8]}.png"
        output_path = images_dir / filename

        if await self.provider.download_image(image_url, output_path):
            return self._to_relative_path(output_path)
        return None
