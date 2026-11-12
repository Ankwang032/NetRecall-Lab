from pathlib import Path

from backend.services.concept_sync import plan_sync
from integrations.sources.markdown import MarkdownConceptSource
from scripts.preview_concepts import main

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "concepts"


def test_samples_parse_without_errors_or_dangling_refs():
    source = MarkdownConceptSource(SAMPLES)
    p = plan_sync(source.source_type, source.fetch_all(), existing=[])
    assert p.errors == []
    assert p.dangling_refs == []
    assert sorted(c.concept_id for c in p.created) == ["NET-001", "NET-005", "NET-010"]
    assert all(c.questions for c in p.created)


def test_preview_exits_0_for_samples(capsys):
    assert main([str(SAMPLES)]) == 0
    assert "NET-010" in capsys.readouterr().out


def test_preview_exits_1_on_read_error(tmp_path, capsys):
    (tmp_path / "bad.md").write_text("frontmatter 없음", encoding="utf-8")
    assert main([str(tmp_path)]) == 1
    assert "bad.md" in capsys.readouterr().err


def test_preview_warns_on_dangling_ref_but_exits_0(tmp_path, capsys):
    (tmp_path / "a.md").write_text("---\nid: NET-001\nrelated: [NET-999]\n---\n본문\n",
                                   encoding="utf-8")
    assert main([str(tmp_path)]) == 0
    assert "NET-999" in capsys.readouterr().out


def test_preview_exits_1_for_missing_folder(tmp_path):
    assert main([str(tmp_path / "missing")]) == 1
