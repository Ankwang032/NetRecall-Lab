"""question kind: 원래 질문(AI 변형 없음)도 출제한다

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16 23:40:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 기존 행은 모두 AI 변형 질문이다
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=16), server_default='variant', nullable=False))
        batch_op.alter_column('relative_difficulty', existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('difficulty_reason', existing_type=sa.Text(), nullable=True)
        batch_op.alter_column('model', existing_type=sa.String(length=100), nullable=True)
        batch_op.alter_column('prompt_version', existing_type=sa.String(length=32), nullable=True)


def downgrade() -> None:
    # 원래 질문은 이전 스키마에 담을 수 없어 답안·평가와 함께 지운다
    originals = "SELECT id FROM questions WHERE kind = 'original'"
    submissions = f"SELECT id FROM answer_submissions WHERE question_id IN ({originals})"
    op.execute(f"DELETE FROM answer_evaluations WHERE submission_id IN ({submissions})")
    op.execute(f"DELETE FROM answer_submissions WHERE question_id IN ({originals})")
    op.execute("DELETE FROM questions WHERE kind = 'original'")
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.alter_column('prompt_version', existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column('model', existing_type=sa.String(length=100), nullable=False)
        batch_op.alter_column('difficulty_reason', existing_type=sa.Text(), nullable=False)
        batch_op.alter_column('relative_difficulty', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('kind')
