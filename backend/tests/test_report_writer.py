from pathlib import Path

from app.storage.report_writer import ReportWriter


def test_write_and_resolve_safe(tmp_path: Path):
    writer = ReportWriter(reports_dir=tmp_path)
    out = writer.write_markdown("hello topic", "# report")
    assert out.exists()
    assert writer.resolve_safe(str(out)) is not None

