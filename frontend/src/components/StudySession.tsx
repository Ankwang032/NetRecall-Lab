import { useRef, useState } from "react";
import { ArrowLeftIcon, ShuffleIcon, SpinnerIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api, errorMessage, type DueCard, type Question, type ReviewResult } from "@/api";
import { AnswerRound } from "@/components/AnswerRound";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { formatKst } from "@/lib/format";
import { cn } from "@/lib/utils";

type Props = { cards: DueCard[]; onExit: () => void };

// 카드를 순서대로 한 장씩 학습한다. 등급을 고르면 다음 카드로 넘어간다
export function StudySession({ cards, onExit }: Props) {
  const [index, setIndex] = useState(0);
  const card = cards[index];

  function rated(result: ReviewResult) {
    const next = `다음 복습: ${formatKst(result.next_due_at)}`;
    if (index + 1 < cards.length) {
      toast.success("저장했습니다", { description: next });
      setIndex(index + 1);
    } else {
      toast.success("이번 학습을 마쳤습니다", { description: next });
      onExit();
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" onClick={onExit} className="-ml-2.5">
          <ArrowLeftIcon aria-hidden /> 목록
        </Button>
        <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
          <span className="tabular-nums">{index + 1} / {cards.length}</span>
          <Progress value={(index / cards.length) * 100} aria-label="학습 진행" className="w-24" />
        </div>
      </div>
      <CardStudy key={card.card_id} card={card} onRated={rated} />
    </div>
  );
}

// 1차: 원래 질문에 답하고 AI 평가 → (필요하면) 2차: AI 변형 질문 → 등급 선택
function CardStudy({ card, onRated }: { card: DueCard; onRated: (r: ReviewResult) => void }) {
  const original = useRef<Question | null>(null); // 평가가 실패해 다시 낼 때 질문을 또 만들지 않는다
  const [firstDone, setFirstDone] = useState(false);
  const [variant, setVariant] = useState<Question | null>(null);
  const [variantBusy, setVariantBusy] = useState(false);
  const [variantError, setVariantError] = useState<string | null>(null);

  async function submitOriginal(answer: string) {
    original.current ??= await api.createOriginalQuestion(card.card_id);
    return api.submitAnswer(original.current.question_id, answer);
  }

  async function requestVariant() {
    setVariantBusy(true);
    setVariantError(null);
    try {
      setVariant(await api.createVariantQuestion(card.card_id));
    } catch (e) {
      setVariantError(errorMessage(e));
    } finally {
      setVariantBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-mono">{card.concept_id}</Badge>
        <span className="font-medium">{card.concept_title}</span>
      </div>

      <AnswerRound
        step="1차"
        label="원래 질문"
        question={card.question}
        submit={submitOriginal}
        onEvaluated={() => setFirstDone(true)}
      />

      {firstDone && !variant && (
        <Card size="sm">
          <CardContent className="flex flex-wrap items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="font-medium">한 번 더 확인하기</p>
              <p className="text-sm text-muted-foreground">
                외운 답이 아닌지, 같은 개념을 다른 상황이나 수치로 바꾼 질문으로 확인합니다
              </p>
            </div>
            <Button variant="outline" size="lg" onClick={requestVariant} disabled={variantBusy}>
              {variantBusy ? <SpinnerIcon className="animate-spin" aria-hidden /> : <ShuffleIcon aria-hidden />}
              {variantBusy ? "질문 만드는 중…" : "변형 질문 받기"}
            </Button>
            {variantError && (
              <Alert variant="destructive" className="basis-full">
                <WarningCircleIcon aria-hidden />
                <AlertTitle>변형 질문을 만들지 못했습니다</AlertTitle>
                <AlertDescription>{variantError}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      {variant && (
        <AnswerRound
          step="2차"
          label="AI 변형 질문"
          question={variant.question}
          difficulty={
            variant.relative_difficulty === null
              ? undefined
              : { value: variant.relative_difficulty, reason: variant.difficulty_reason ?? "" }
          }
          submit={(answer) => api.submitAnswer(variant.question_id, answer)}
          onEvaluated={() => {}}
        />
      )}

      {firstDone && <RatingPanel cardId={card.card_id} onRated={onRated} />}
    </div>
  );
}

const RATINGS = [
  { value: 1, label: "Again", hint: "기억 못함", dot: "bg-destructive" },
  { value: 2, label: "Hard", hint: "어렵게 기억", dot: "bg-warning" },
  { value: 3, label: "Good", hint: "기억함", dot: "bg-primary" },
  { value: 4, label: "Easy", hint: "쉽게 기억", dot: "bg-success" },
];

function RatingPanel({ cardId, onRated }: { cardId: number; onRated: (r: ReviewResult) => void }) {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function rate(value: number) {
    setBusy(value);
    setError(null);
    try {
      onRated(await api.review(cardId, value));
    } catch (e) {
      setError(errorMessage(e));
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <h2 className="text-base font-semibold">얼마나 잘 기억했나요?</h2>
        <CardDescription>AI 점수와 별개로 직접 고릅니다. 고른 등급으로 다음 복습일이 정해집니다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {RATINGS.map((r) => (
            <Button
              key={r.value}
              variant="outline"
              className="h-auto flex-col gap-0.5 py-3"
              onClick={() => rate(r.value)}
              disabled={busy !== null}
            >
              <span className="flex items-center gap-1.5 font-semibold">
                {busy === r.value ? (
                  <SpinnerIcon className="animate-spin" aria-hidden />
                ) : (
                  <span className={cn("size-2 rounded-full", r.dot)} aria-hidden />
                )}
                {r.label}
              </span>
              <span className="text-xs font-normal text-muted-foreground">{r.hint}</span>
            </Button>
          ))}
        </div>
        {error && (
          <Alert variant="destructive">
            <WarningCircleIcon aria-hidden />
            <AlertTitle>저장하지 못했습니다</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
