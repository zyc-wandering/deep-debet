from pathlib import Path

from app.storage.report_writer import ReportWriter


def test_write_and_resolve_safe(tmp_path: Path, monkeypatch):
    # Point debates_dir to tmp_path so resolve_safe works
    from app.config import settings
    object.__setattr__(settings, "debates_dir", tmp_path)

    writer = ReportWriter()
    debate_dir = tmp_path / "test-topic_20260315"
    debate_dir.mkdir()
    out = writer.write_markdown(debate_dir, "# report")
    assert out.exists()
    assert out.name == "report.md"
    assert writer.resolve_safe(str(out)) is not None
