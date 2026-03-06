from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.utils.formatting import slugify, utc_now_compact


class ReportWriter:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or settings.reports_dir

    def write_markdown(self, topic: str, content: str) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{slugify(topic)}_{utc_now_compact()}.md"
        path = self.reports_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def resolve_safe(self, raw_path: str) -> Path | None:
        p = Path(raw_path).expanduser().resolve()
        root = self.reports_dir.resolve()
        try:
            p.relative_to(root)
            return p
        except Exception:
            return None

