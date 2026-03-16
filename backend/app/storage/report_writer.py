from __future__ import annotations

from pathlib import Path

from app.config import settings


class ReportWriter:
    def write_markdown(self, debate_dir: Path | str, content: str) -> Path:
        """Write report.md into the debate directory."""
        debate_dir = Path(debate_dir)
        debate_dir.mkdir(parents=True, exist_ok=True)
        path = debate_dir / "report.md"
        path.write_text(content, encoding="utf-8")
        return path

    def resolve_safe(self, raw_path: str) -> Path | None:
        """Validate that the given path is within the debates directory."""
        p = Path(raw_path).expanduser().resolve()
        root = settings.debates_dir.resolve()
        try:
            p.relative_to(root)
            return p
        except Exception:
            return None
