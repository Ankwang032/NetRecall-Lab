import pytest
from sqlalchemy import select

from backend.database import init_db, make_engine, make_session_factory
from backend.models import AnswerEvaluation, AnswerSubmission, Question, ReviewCard
from backend.models.concept import utcnow
from backend.services import ai_prompts as prompts
from backend.services.assessment_service import QuestionNotFound, evaluate_answer, generate_question
from backend.services.concept_store import sync_source
from backend.services.review_service import CardNotFound, CardNotReviewable
from integrations.llm import LLMError
from integrations.sources.markdown import MarkdownConceptSource
from tests.fakes import FakeLLM

VARIANT = prompts.VariantQuestion(
    question="변형 질문", relative_difficulty=1, difficulty_reason="계산 단계가 하나 더 있다",
)


def evaluation(**overrides):
    fields = dict(score=80, accuracy=90, completeness=70, logic=85, technical_validity=80,
                  application=60, strengths=["잘함"], missing_points=["빠짐"],
                  technical_errors=[], recommended_lab="LAB-001")
    return prompts.AnswerEvaluation(**(fields | overrides))


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "concepts"
    d.mkdir()
    return d


def write(root, questions="Q1, Q2, Q3"):
    path = root / "a.md"
    path.write_text(
        f"---\nid: NET-010\ntitle: Static Routing\nkeywords: [Next Hop]\nlabs: [LAB-001]\n"
        f"questions: [{questions}]\n---\n라우팅 본문\n",
        encoding="utf-8",
    )
    return path


def sync(session, root):
    sync_source(session, MarkdownConceptSource(root))


def card_id(session, question="Q1"):
    return session.scalars(select(ReviewCard.id).where(ReviewCard.question == question)).one()


@pytest.fixture
def card(session, root):
    write(root)
    sync(session, root)
    return card_id(session)


@pytest.fixture
def question(session, card):
    return generate_question(session, FakeLLM(VARIANT), card, utcnow()).id


# ---- 질문 생성 ----

def test_generates_variant_with_difficulty_in_one_call(session, card):
    llm = FakeLLM(VARIANT)
    q = generate_question(session, llm, card, utcnow())

    assert (q.card_id, q.concept_id, q.base_question, q.question) == (card, "NET-010", "Q1", "변형 질문")
    assert (q.relative_difficulty, q.difficulty_reason) == (1, "계산 단계가 하나 더 있다")
    assert (q.model, q.prompt_version) == ("fake-model", prompts.PROMPT_VERSION)

    (call,) = llm.calls  # 무료 등급 한도 때문에 난이도도 같은 호출에서 받는다
    assert (call["schema"], call["system"]) == (prompts.VariantQuestion, prompts.VARIANT_SYSTEM)
    assert "라우팅 본문" in call["prompt"] and "Q1" in call["prompt"]


def test_unknown_card_raises_without_calling_llm(session):
    llm = FakeLLM()
    with pytest.raises(CardNotFound):
        generate_question(session, llm, 999, utcnow())
    assert llm.calls == []


def test_inactive_card_and_archived_concept_are_rejected(session, root, card):
    write(root, questions="Q2, Q3, Q4")  # Q1 카드 비활성
    sync(session, root)
    with pytest.raises(CardNotReviewable):
        generate_question(session, FakeLLM(), card, utcnow())

    (root / "a.md").unlink()  # 개념 보관
    sync(session, root)
    with pytest.raises(CardNotReviewable):
        generate_question(session, FakeLLM(), card_id(session, "Q2"), utcnow())


def test_llm_failure_stores_no_question(session, card):
    with pytest.raises(LLMError):
        generate_question(session, FakeLLM(LLMError("생성 실패")), card, utcnow())
    assert session.scalars(select(Question)).all() == []


# ---- 답안 평가 ----

def test_evaluates_answer_and_stores_both(session, question):
    llm = FakeLLM(evaluation())
    submission, ev = evaluate_answer(session, llm, question, "내 답안", utcnow())

    assert (submission.question_id, submission.answer) == (question, "내 답안")
    assert (ev.submission_id, ev.score, ev.model) == (submission.id, 80, "fake-model")
    assert ev.feedback_json["application"] == 60
    assert ev.feedback_json["recommended_lab"] == "LAB-001"

    (call,) = llm.calls
    assert call["schema"] is prompts.AnswerEvaluation
    for text in ("라우팅 본문", "Q1", "변형 질문", "내 답안", "LAB-001"):
        assert text in call["prompt"]


def test_lab_not_linked_to_concept_is_dropped(session, question):
    _, ev = evaluate_answer(session, FakeLLM(evaluation(recommended_lab="LAB-999")),
                            question, "답", utcnow())
    assert ev.feedback_json["recommended_lab"] is None


def test_llm_failure_stores_no_answer(session, question):
    with pytest.raises(LLMError):
        evaluate_answer(session, FakeLLM(LLMError("평가 실패")), question, "답", utcnow())
    assert session.scalars(select(AnswerSubmission)).all() == []
    assert session.scalars(select(AnswerEvaluation)).all() == []


def test_unknown_question_raises(session):
    with pytest.raises(QuestionNotFound):
        evaluate_answer(session, FakeLLM(), 999, "답", utcnow())


@pytest.mark.parametrize("field, value", [("score", 101), ("application", -1)])
def test_evaluation_scores_must_be_0_to_100(field, value):
    with pytest.raises(ValueError):
        evaluation(**{field: value})


@pytest.mark.parametrize("value", [-3, 3])
def test_relative_difficulty_must_be_minus2_to_2(value):
    with pytest.raises(ValueError):
        prompts.VariantQuestion(question="질문", relative_difficulty=value, difficulty_reason="이유")
