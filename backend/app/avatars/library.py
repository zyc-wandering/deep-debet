from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


AVATAR_LIBRARY_PREFIX = "avatar-library/"
APP_DIR = Path(__file__).resolve().parents[1]
AVATAR_LIBRARY_DIR = APP_DIR / "static" / "avatar_library"
AVATAR_IMAGE_DIR = AVATAR_LIBRARY_DIR / "images"
AVATAR_MANIFEST_PATH = AVATAR_LIBRARY_DIR / "manifest.json"
ALLOWED_ETHNICITIES = {
    "east_asian",
    "south_asian",
    "middle_eastern",
    "black_african",
    "white_european",
    "latine",
    "southeast_asian",
}
ALLOWED_SKIN_TONES = {"light", "medium", "tan", "dark"}
ALLOWED_GENDERS = {"male", "female", "nonbinary", "unknown"}


@dataclass(frozen=True)
class AvatarAsset:
    id: str
    src: str
    name: str
    ethnicity: str
    skin_tone: str
    gender: str
    tags: tuple[str, ...] = ()


class AvatarLibrary:
    """Local avatar matcher backed by a checked-in manifest and image files."""

    def __init__(self, manifest_path: Path = AVATAR_MANIFEST_PATH) -> None:
        self.manifest_path = manifest_path
        self.library_dir = manifest_path.parent
        self.image_dir = self.library_dir / "images"
        self.assets = self._load_assets(manifest_path)

    def assign_to_debaters(self, debaters: Iterable[Any], session_id: str) -> dict[str, str]:
        avatars: dict[str, str] = {}
        used_ids: set[str] = set()
        debater_list = list(debaters)

        for debater in debater_list:
            asset = self.choose(debater, session_id=session_id, used_ids=used_ids)
            if not asset:
                continue
            used_ids.add(asset.id)
            setattr(debater, "avatar_id", asset.id)
            setattr(debater, "avatar_url", asset.src)
            avatars[getattr(debater, "name", asset.name)] = asset.src

        return avatars

    def choose(
        self,
        debater: Any,
        *,
        session_id: str,
        used_ids: set[str] | None = None,
    ) -> AvatarAsset | None:
        if not self.assets:
            return None

        used_ids = used_ids or set()
        candidates = [asset for asset in self.assets if asset.id not in used_ids]
        if not candidates:
            candidates = list(self.assets)

        profile = self.profile_for(debater)
        candidates = self._restrict_if_available(
            candidates,
            profile["gender"] != "unknown",
            lambda asset: asset.gender == profile["gender"],
        )
        candidates = self._restrict_if_available(
            candidates,
            bool(profile["ethnicity"]),
            lambda asset: asset.ethnicity == profile["ethnicity"],
        )
        candidates = self._restrict_if_available(
            candidates,
            bool(profile["skin_tone"]),
            lambda asset: asset.skin_tone == profile["skin_tone"],
        )

        scored = [
            (self._score(asset, profile), self._tie_break(session_id, debater, asset), asset)
            for asset in candidates
        ]
        scored.sort(key=lambda item: (-item[0], item[1], item[2].id))
        return scored[0][2]

    def profile_for(self, debater: Any) -> dict[str, Any]:
        text = self._debater_text(debater)
        gender = _normalize_gender(getattr(debater, "gender", "") or _value_from_mapping(debater, "gender"))
        ethnicity = _infer_ethnicity(text)
        skin_tone = _infer_skin_tone(text, ethnicity)
        tags = _infer_tags(text)
        return {
            "gender": gender,
            "ethnicity": ethnicity,
            "skin_tone": skin_tone,
            "tags": tags,
            "text": text,
        }

    def resolve_path(self, path: str) -> Path | None:
        normalized = path.replace("\\", "/")
        if not normalized.startswith(AVATAR_LIBRARY_PREFIX):
            return None

        filename = normalized[len(AVATAR_LIBRARY_PREFIX) :].strip("/")
        if not filename or "/" in filename:
            return None

        image_path = (self.image_dir / filename).resolve()
        try:
            image_path.relative_to(self.image_dir.resolve())
        except ValueError:
            return None

        if not image_path.exists() or not image_path.is_file():
            return None
        return image_path

    def _load_assets(self, manifest_path: Path) -> list[AvatarAsset]:
        try:
            raw_assets = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        assets: list[AvatarAsset] = []
        for raw in raw_assets:
            if not isinstance(raw, dict):
                continue
            try:
                asset = AvatarAsset(
                    id=str(raw["id"]),
                    src=str(raw["src"]),
                    name=str(raw["name"]),
                    ethnicity=str(raw["ethnicity"]),
                    skin_tone=str(raw["skin_tone"]),
                    gender=str(raw["gender"]),
                    tags=tuple(str(tag) for tag in raw.get("tags", []) if tag),
                )
            except KeyError:
                continue
            if self.resolve_path(asset.src):
                assets.append(asset)
        return assets

    def _score(self, asset: AvatarAsset, profile: dict[str, Any]) -> int:
        score = 0
        gender = profile["gender"]
        if gender != "unknown":
            if asset.gender == gender:
                score += 12
            elif asset.gender != "unknown":
                score -= 12

        ethnicity = profile["ethnicity"]
        if ethnicity and asset.ethnicity == ethnicity:
            score += 10
        elif ethnicity:
            score -= 4

        skin_tone = profile["skin_tone"]
        if skin_tone and asset.skin_tone == skin_tone:
            score += 6

        tags = profile["tags"]
        score += 4 * len(tags.intersection(asset.tags))
        return score

    def _restrict_if_available(self, candidates, enabled, predicate):
        if not enabled:
            return candidates
        filtered = [asset for asset in candidates if predicate(asset)]
        return filtered or candidates

    def _debater_text(self, debater: Any) -> str:
        fields = [
            "name",
            "gender",
            "ethnicity",
            "background",
            "stance",
            "personality",
            "speaking_style",
        ]
        values = [str(getattr(debater, field, "") or _value_from_mapping(debater, field)) for field in fields]
        return " ".join(values).lower()

    def _tie_break(self, session_id: str, debater: Any, asset: AvatarAsset) -> str:
        debater_id = str(getattr(debater, "id", "") or _value_from_mapping(debater, "id"))
        digest_input = f"{session_id}:{debater_id}:{asset.id}"
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def _value_from_mapping(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key, "")
    return ""


def _normalize_gender(value: str) -> str:
    text = value.strip().lower()
    if text in {"male", "man", "masculine", "m", "男", "男性", "男士"}:
        return "male"
    if text in {"female", "woman", "feminine", "f", "女", "女性", "女士"}:
        return "female"
    if text in {"nonbinary", "non-binary", "non_binary", "nb", "非二元"}:
        return "nonbinary"
    return "unknown"


ETHNICITY_KEYWORDS = {
    "east_asian": [
        "east asian",
        "chinese",
        "china",
        "japanese",
        "korean",
        "中国",
        "华人",
        "日本",
        "韩国",
        "zhang",
        "chen",
        "li wei",
        "wang",
        "lin",
        "liu",
        "zhao",
        "zhou",
        "tanaka",
        "sato",
    ],
    "south_asian": [
        "south asian",
        "indian",
        "india",
        "pakistani",
        "bangladeshi",
        "印度",
        "孟加拉",
        "patel",
        "mehta",
        "sharma",
        "priya",
        "aarav",
        "raj",
    ],
    "middle_eastern": [
        "middle eastern",
        "arab",
        "iranian",
        "iran",
        "turkish",
        "阿拉伯",
        "伊朗",
        "hassan",
        "fatima",
        "karim",
        "jaber",
        "hamid",
        "reza",
        "al-",
    ],
    "black_african": [
        "black",
        "african",
        "nigerian",
        "kenyan",
        "ghanaian",
        "黑人",
        "非洲",
        "diallo",
        "okonkwo",
        "mbeki",
        "mensah",
        "omondi",
        "juma",
        "kamau",
    ],
    "white_european": [
        "white",
        "caucasian",
        "european",
        "british",
        "irish",
        "german",
        "italian",
        "nordic",
        "美国白人",
        "欧洲",
        "lars",
        "jensen",
        "klaus",
        "richter",
        "rossi",
        "svensson",
        "o'connor",
        "liam",
    ],
    "latine": [
        "latin",
        "latine",
        "latino",
        "latina",
        "hispanic",
        "mexican",
        "spanish",
        "mendez",
        "martinez",
    ],
    "southeast_asian": [
        "southeast asian",
        "indonesian",
        "malaysian",
        "vietnamese",
        "thai",
        "filipino",
        "印尼",
        "越南",
        "泰国",
        "pratama",
    ],
}

SKIN_TONE_KEYWORDS = {
    "light": ["light skin", "fair skin", "white", "白人", "浅肤"],
    "medium": ["medium skin", "olive skin", "latine", "hispanic", "中等肤色"],
    "tan": ["tan skin", "brown skin", "south asian", "middle eastern", "棕色", "小麦色"],
    "dark": ["dark skin", "black", "african", "深肤", "黑人"],
}

ETHNICITY_DEFAULT_SKIN_TONE = {
    "east_asian": "light",
    "south_asian": "tan",
    "middle_eastern": "tan",
    "black_african": "dark",
    "white_european": "light",
    "latine": "medium",
    "southeast_asian": "tan",
}

TAG_KEYWORDS = {
    "policy": ["policy", "governance", "government", "regulator", "制度", "政策", "治理"],
    "finance": ["finance", "market", "central bank", "gold", "经济", "金融", "市场", "央行"],
    "academic": ["academic", "scholar", "research", "professor", "博士", "教授", "研究", "学者"],
    "operator": ["operator", "founder", "entrepreneur", "manager", "startup", "经营", "企业", "创始"],
    "legal": ["law", "legal", "lawyer", "court", "法律", "律师", "司法"],
    "security": ["security", "military", "colonel", "defense", "安全", "军事", "国防"],
    "technology": ["technology", "engineer", "ai", "software", "技术", "工程", "人工智能"],
    "labor": ["labor", "union", "worker", "employment", "工会", "劳动", "就业"],
    "community": ["community", "grassroots", "activist", "社区", "基层"],
    "geopolitics": ["geopolitics", "foreign policy", "war", "外交", "战争", "地缘"],
}


def _infer_ethnicity(text: str) -> str:
    for ethnicity, keywords in ETHNICITY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return ethnicity
    return ""


def _infer_skin_tone(text: str, ethnicity: str) -> str:
    for skin_tone, keywords in SKIN_TONE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return skin_tone
    return ETHNICITY_DEFAULT_SKIN_TONE.get(ethnicity, "")


def _infer_tags(text: str) -> set[str]:
    return {
        tag
        for tag, keywords in TAG_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }


_avatar_library: AvatarLibrary | None = None


def get_avatar_library() -> AvatarLibrary:
    global _avatar_library
    if _avatar_library is None:
        _avatar_library = AvatarLibrary()
    return _avatar_library
