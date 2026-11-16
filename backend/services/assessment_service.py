"""AI 변형 질문 생성과 답안 평가.

LLM 호출은 몇 초 걸린다. 그동안 SQLite를 잡고 있지 않도록, 필요한 값을 읽은 뒤 트랜잭션을 끝내고
호출한다. 결과는 새 트랜잭션에서 저장한다. LLM이 실패하면 아무것도 저장하지 않는다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AnswerEvaluation, AnswerSubmission, Concept, ConceptLab, Question, ReviewCard
from backend.services import ai_prompts as prompts
from backend.services.review_service import CardNotFound, CardNotReviewable
from integrations.llm import LLMClient


class QuestionNotFound(LookupError):
    pass


def generate_question(session: Session, llm: LLMClient, card_id: int, now: datetime) -> Question:
    """카드 질문을 변형하고, 같은 호출에서 받은 원래 질문 대비 난이도와 함께 저장한다."""
    try:
        card = session.get(ReviewCard, card_id)
        if card is None:
            raise CardNotFound(card_id)
        concept = session.get_one(Concept, card.concept_id)
        if not card.active or concept.archived:
            raise CardNotReviewable(card_id)
        context, concept_id, base = _context(concept), concept.id, card.question
        session.rollback()  # LLM 호출 동안 읽기 트랜잭션을 잡지 않는다

        variant = llm.generate(
            system=prompts.VARIANT_SYSTEM, prompt=prompts.variant_prompt(context, base),
            schema=prompts.VariantQuestion,
        )

        question = Question(
            card_id=card_id, concept_id=concept_id, base_question=base, question=variant.question,
            relative_difficulty=variant.relative_difficulty, difficulty_reason=variant.difficulty_reason,
            model=llm.model, prompt_version=prompts.PROMPT_VERSION, created_at=now,
        )
        session.add(question)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return question


def evaluate_answer(
    session: Session, llm: LLMClient, question_id: int, answer: str, now: datetime,
) -> tuple[AnswerSubmission, AnswerEvaluation]:
    """답안을 평가하고 답안과 평가를 한 트랜잭션으로 저장한다."""
    try:
        question = session.get(Question, question_id)
        if question is None:
            raise QuestionNotFound(question_id)
        concept = session.get_one(Concept, question.concept_id)
        labs = list(session.scalars(
            select(ConceptLab.scenario_id).where(ConceptLab.concept_id == concept.id)
            .order_by(ConceptLab.scenario_id)
        ))
        context, base, asked = _context(concept), question.base_question, question.question
        session.rollback()  # LLM 호출 동안 읽기 트랜잭션을 잡지 않는다

        result = llm.generate(
            system=prompts.EVALUATION_SYSTEM,
            prompt=prompts.evaluation_prompt(context, base, asked, answer, labs),
            schema=prompts.AnswerEvaluation,
        )
        if result.recommended_lab not in labs:  # 개념에 연결되지 않은 실습은 버린다
            result = result.model_copy(update={"recommended_lab": None})

        submission = AnswerSubmission(question_id=question_id, answer=answer, submitted_at=now)
        session.add(submission)
        session.flush()
        evaluation = AnswerEvaluation(
            submission_id=submission.id, score=result.score, feedback_json=result.model_dump(),
            model=llm.model, prompt_version=prompts.PROMPT_VERSION, created_at=now,
        )
        session.add(evaluation)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return submission, evaluation


def _context(concept: Concept) -> prompts.ConceptContext:
    return prompts.ConceptContext(
        title=concept.title, keywords=list(concept.keywords), content=concept.content,
    )
