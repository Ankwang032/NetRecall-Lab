import pytest

from integrations.sources.base import SourceItem
from integrations.sources.markdown import MarkdownConceptSource, MarkdownParseError


def concept(cid: str, body: str = "본문") -> str:
    return f"---\nid: {cid}\n---\n{body}\n"


def write(root, rel: str, text: str):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "concepts"
    d.mkdir()
    return d


def refs(source):
    return [i.source_ref for i in source.list_items()]


def test_lists_nested_files_in_sorted_posix_order(root):
    write(root, "b.md", concept("NET-002"))
    write(root, "net/a.md", concept("NET-001"))
    write(root, "notes.txt", "무시")
    assert refs(MarkdownConceptSource(root)) == ["b.md", "net/a.md"]


def test_skips_hidden_underscore_templates_and_readme(root):
    write(root, "real.md", concept("NET-001"))
    for rel in [".hidden/a.md", ".obsidian/b.md", "_drafts/c.md", "_d.md",
                "templates/t.md", "sub/templates/t.md", "node_modules/x.md",
                "README.md", "sub/readme.md"]:
        write(root, rel, concept("NET-999"))
    assert refs(MarkdownConceptSource(root)) == ["real.md"]


def test_skips_symlinks(root, tmp_path):
    outside = write(tmp_path, "outside.md", concept("NET-001"))
    (root / "link.md").symlink_to(outside)
    assert refs(MarkdownConceptSource(root)) == []


def test_fetch_refuses_paths_outside_root(root, tmp_path):
    write(tmp_path, "outside.md", concept("NET-001"))
    with pytest.raises(MarkdownParseError, match="밖"):
        MarkdownConceptSource(root).fetch(SourceItem("../outside.md"))


def test_root_must_be_directory(tmp_path):
    with pytest.raises(NotADirectoryError):
        MarkdownConceptSource(tmp_path / "missing")


def test_handles_bom_and_crlf(root):
    (root / "win.md").write_bytes(
        "﻿---\r\nid: NET-001\r\n---\r\n# 제목\r\n본문\r\n".encode("utf-8"))
    c = MarkdownConceptSource(root).fetch(SourceItem("win.md"))
    assert c.title == "제목"
    assert "\r" not in c.content


def test_file_size_limit_is_reported_as_error(root):
    write(root, "big.md", concept("NET-001", "가" * 200))
    result = MarkdownConceptSource(root, max_file_bytes=100).fetch_all()
    assert result.concepts == []
    assert result.errors[0].source_ref == "big.md"
    assert "너무 큽니다" in result.errors[0].message


def test_bad_file_does_not_stop_other_files(root):
    write(root, "a.md", concept("NET-001"))
    write(root, "b.md", "frontmatter 없음")
    (root / "c.md").write_bytes(b"---\nid: NET-003\n---\n\xff\xfe")
    write(root, "d.md", concept("NET-004"))
    result = MarkdownConceptSource(root).fetch_all()
    assert [c.concept_id for c in result.concepts] == ["NET-001", "NET-004"]
    assert [e.source_ref for e in result.errors] == ["b.md", "c.md"]


def test_duplicate_id_keeps_first_file_in_path_order(root):
    write(root, "b.md", concept("NET-001", "나중"))
    write(root, "a.md", concept("NET-001", "먼저"))
    result = MarkdownConceptSource(root).fetch_all()
    assert [c.source_ref for c in result.concepts] == ["a.md"]
    assert result.errors[0].source_ref == "b.md"
    assert "a.md" in result.errors[0].message
