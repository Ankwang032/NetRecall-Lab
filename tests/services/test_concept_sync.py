from dataclasses import replace

from backend.services.concept_sync import ExistingConcept, plan_sync
from integrations.sources.base import FetchResult, RawConcept, SourceError


def concept(cid="NET-001", ref="a.md", content="본문", questions=("Q1", "Q2", "Q3"), **extra):
    c = RawConcept(concept_id=cid, title=cid, content=content,
                   source_type="markdown", source_ref=ref, questions=questions, **extra)
    return replace(c, content_hash=c.compute_hash())


def stored(c, archived=False, source_type="markdown"):
    return ExistingConcept(c.concept_id, source_type, c.source_ref, c.content_hash, archived)


def plan(concepts=(), existing=(), errors=()):
    return plan_sync("markdown", FetchResult(list(concepts), list(errors)), list(existing))


def ids(items):
    return [c.concept_id for c in items]


def test_new_concept_is_created():
    p = plan([concept()])
    assert ids(p.created) == ["NET-001"]
    assert p.has_changes


def test_content_change_is_updated():
    old = concept(content="옛 본문")
    p = plan([concept(content="새 본문")], [stored(old)])
    assert ids(p.updated) == ["NET-001"]


def test_same_content_same_place_is_unchanged():
    c = concept()
    p = plan([c], [stored(c)])
    assert p.unchanged == ["NET-001"]
    assert not p.has_changes


def test_move_with_same_content_is_relocated():
    p = plan([concept(ref="new/place.md")], [stored(concept(ref="a.md"))])
    assert ids(p.relocated) == ["NET-001"]
    assert p.updated == []


def test_move_with_content_change_is_updated():
    p = plan([concept(ref="b.md", content="새")], [stored(concept(ref="a.md"))])
    assert ids(p.updated) == ["NET-001"] and p.relocated == []


def test_missing_concept_is_archived():
    p = plan([], [stored(concept())])
    assert p.archived == ["NET-001"]


def test_already_archived_concept_is_not_archived_again():
    p = plan([], [stored(concept(), archived=True)])
    assert p.archived == [] and not p.has_changes


def test_archived_concept_that_reappears_is_restored():
    c = concept()
    p = plan([c], [stored(c, archived=True)])
    assert ids(p.restored) == ["NET-001"]


def test_concept_in_unreadable_file_is_kept():
    p = plan([], [stored(concept(ref="a.md"))], [SourceError("a.md", "YAML 오류")])
    assert p.kept_due_to_error == ["NET-001"]
    assert p.archived == []
    assert len(p.errors) == 1


def test_id_owned_by_other_source_is_conflict():
    other = stored(concept(), source_type="notion")
    p = plan([concept()], [other])
    assert not p.has_changes
    assert "notion" in p.errors[0].message


def test_other_source_concepts_are_never_archived():
    p = plan([], [stored(concept(), source_type="notion")])
    assert p.archived == []


def test_dangling_refs_are_warned_but_concept_is_created():
    c = concept(prerequisites=("NET-999",), related=("NET-002",))
    p = plan([c, concept("NET-002", "b.md")])
    assert ids(p.created) == ["NET-001", "NET-002"]
    assert p.dangling_refs == [("NET-001", "NET-999")]


def test_ref_to_existing_concept_is_not_dangling():
    p = plan([concept(prerequisites=("NET-002",))], [stored(concept("NET-002", "b.md"))],
             [SourceError("b.md", "오류")])
    assert p.dangling_refs == []


def test_ref_to_concept_archived_now_is_dangling():
    p = plan([concept(prerequisites=("NET-002",))], [stored(concept("NET-002", "b.md"))])
    assert p.archived == ["NET-002"]
    assert p.dangling_refs == [("NET-001", "NET-002")]


def test_summary_counts():
    p = plan([concept()], [stored(concept("NET-002", "b.md"))])
    s = p.summary()
    assert s["created"] == 1 and s["archived"] == 1 and s["errors"] == 0


# ---- 질문 최소 개수 (소스와 무관한 규칙) ----

def test_concept_with_too_few_questions_is_error():
    p = plan([concept(questions=("Q1", "Q2"))])
    assert p.created == []
    assert p.errors[0].source_ref == "a.md"
    assert "3개 이상" in p.errors[0].message and "현재 2개" in p.errors[0].message


def test_too_few_questions_keeps_stored_concept():
    old = concept()
    p = plan([concept(content="새 본문", questions=("Q1",))], [stored(old)])
    assert p.kept_due_to_error == ["NET-001"]
    assert not p.has_changes


def test_too_few_questions_after_move_still_keeps_stored_concept():
    # 경로가 바뀌어도 id로 알아보므로 보관하지 않는다
    old = concept()
    p = plan([concept(ref="moved.md", questions=())], [stored(old)])
    assert p.kept_due_to_error == ["NET-001"] and p.archived == []


def test_question_rule_applies_to_every_source():
    c = replace(concept(questions=("Q1",)), source_type="notion", source_ref="page-1")
    p = plan_sync("notion", FetchResult([c], []), [])
    assert p.created == [] and p.errors[0].source_ref == "page-1"
