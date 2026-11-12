from dataclasses import replace

from integrations.sources.base import ConceptSource, RawConcept
from integrations.sources.markdown import MarkdownConceptSource


def make(**overrides):
    fields = dict(concept_id="NET-001", title="T", content="본문",
                  source_type="markdown", source_ref="a.md")
    fields.update(overrides)
    return RawConcept(**fields)


def test_hash_ignores_location_and_source_type():
    base = make()
    assert make(source_ref="moved/b.md").compute_hash() == base.compute_hash()
    assert make(source_type="notion").compute_hash() == base.compute_hash()


def test_hash_changes_with_learning_content():
    base = make().compute_hash()
    assert make(content="다른 본문").compute_hash() != base
    assert make(keywords=("OSI",)).compute_hash() != base
    assert make(questions=("질문?",)).compute_hash() != base


def test_hash_ignores_previous_hash_value():
    c = make()
    assert replace(c, content_hash="stale").compute_hash() == c.compute_hash()


def test_markdown_source_implements_protocol(tmp_path):
    assert isinstance(MarkdownConceptSource(tmp_path), ConceptSource)
