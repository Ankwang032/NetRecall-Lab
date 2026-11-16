import { useState } from "react";
import { api, errorMessage, type DueCard, type Evaluation, type Question, type ReviewResult } from "./api";

// relative_difficulty(-2~2) + 2 를 인덱스로 쓴다
const DIFFICULTY = ["훨씬 쉬움", "쉬움", "비슷함", "어려움", "훨씬 어려움"];

type ScoreKey = "accuracy" | "completeness" | "logic" | "technical_validity" | "application";
const SCORES: [ScoreKey, string][] = [
  ["accuracy", "정확성"],
  ["completeness", "완전성"],
  ["logic", "논리성"],
  ["technical_validity", "기술적 타당성"],
  ["application", "응용력"],
];

const RATINGS = [
  { value: 1, label: "Again", hint: "기억 못함" },
  { value: 2, label: "Hard", hint: "어렵게 기억" },
  { value: 3, label: "Good", hint: "기억함" },
  { value: 4, label: "Easy", hint: "쉽게 기억" },
];

type Props = {
  card: DueCard;
  onDone: (result: ReviewResult) => void;
  onCancel: () => void;
};

// 카드 한 장의 학습: AI 질문 → 답안 → AI 평가 → 등급 선택
export function Study({ card, onDone, onCancel }: Props) {
  const [question, setQuestion] = useState<Question | null>(null);
  const [answer, setAnswer] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run<T>(busyLabel: string, action: () => Promise<T>, then: (value: T) => void) {
    setBusy(busyLabel);
    setError(null);
    try {
      then(await action());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section>
      <button className="link" onClick={onCancel} disabled={busy !== null}>← 목록으로</button>
      <p className="concept">{card.concept_id} · {card.concept_title}</p>

      {question === null ? (
        <>
          <p className="muted">원래 질문: {card.question}</p>
          <button
            className="primary"
            onClick={() => run("질문 만드는 중…", () => api.createQuestion(card.card_id), setQuestion)}
            disabled={busy !== null}
          >
            AI 질문 받기
          </button>
        </>
      ) : (
        <>
          <h2>{question.question}</h2>
          <p className="muted">
            난이도 {DIFFICULTY[question.relative_difficulty + 2]} (원래 질문 대비) — {question.difficulty_reason}
          </p>
        </>
      )}

      {question !== null && evaluation === null && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run("평가하는 중…", () => api.submitAnswer(question.question_id, answer), setEvaluation);
          }}
        >
          <label htmlFor="answer">답안</label>
          <textarea
            id="answer"
            rows={10}
            maxLength={10000}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
          <button type="submit" className="primary" disabled={busy !== null || answer.trim() === ""}>
            답안 제출
          </button>
        </form>
      )}

      {evaluation !== null && (
        <>
          <h3>내 답안</h3>
          <p className="answer">{answer}</p>
          <EvaluationView evaluation={evaluation} />
          <h3>복습 등급</h3>
          <p className="muted">AI 점수와 별개로, 얼마나 잘 기억했는지 직접 고르세요.</p>
          <div className="ratings">
            {RATINGS.map((r) => (
              <button
                key={r.value}
                onClick={() => run("저장하는 중…", () => api.review(card.card_id, r.value), onDone)}
                disabled={busy !== null}
              >
                {r.label}
                <small>{r.hint}</small>
              </button>
            ))}
          </div>
        </>
      )}

      {busy && <p className="muted" aria-live="polite">{busy}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function EvaluationView({ evaluation: ev }: { evaluation: Evaluation }) {
  return (
    <div>
      <h3>AI 평가</h3>
      <p className="score">{ev.score}<small> / 100</small></p>
      <dl className="scores">
        {SCORES.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{ev[key]}</dd>
          </div>
        ))}
      </dl>
      <FeedbackList title="잘한 점" items={ev.strengths} />
      <FeedbackList title="빠진 내용" items={ev.missing_points} />
      <FeedbackList title="기술적 오류" items={ev.technical_errors} />
      {ev.recommended_lab && <p>추천 실습: {ev.recommended_lab}</p>}
      <p className="muted small">평가 모델: {ev.model}</p>
    </div>
  );
}

function FeedbackList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <h4>{title}</h4>
      <ul>
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </>
  );
}
