import { useId, useState } from "react";
import { PaperPlaneRightIcon, SpinnerIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { errorMessage, type Evaluation } from "@/api";
import { EvaluationView } from "@/components/EvaluationView";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

// relative_difficulty(-2~2) + 2 를 인덱스로 쓴다
const DIFFICULTY = ["훨씬 쉬움", "쉬움", "비슷함", "어려움", "훨씬 어려움"];

type Props = {
  step: string;
  label: string;
  question: string;
  difficulty?: { value: number; reason: string };
  submit: (answer: string) => Promise<Evaluation>;
  onEvaluated: () => void;
};

// 질문 하나에 답하고 AI 평가를 받는 단계. 평가가 실패해도 쓴 답안은 지우지 않는다
export function AnswerRound({ step, label, question, difficulty, submit, onEvaluated }: Props) {
  const [answer, setAnswer] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const answerId = useId();
  const hintId = useId();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setEvaluation(await submit(answer));
      onEvaluated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
          <span className="rounded-md bg-accent px-1.5 py-0.5 text-accent-foreground">{step}</span>
          {label}
          {difficulty && (
            <Badge variant="outline">난이도 {DIFFICULTY[difficulty.value + 2]}</Badge>
          )}
        </div>
        <h2 className="text-lg leading-relaxed font-semibold text-balance">{question}</h2>
        {difficulty && <CardDescription>{difficulty.reason}</CardDescription>}
      </CardHeader>

      <CardContent>
        {evaluation ? (
          <>
            <p className="text-xs font-medium text-muted-foreground">내 답안</p>
            <p className="mt-1.5 rounded-lg bg-muted px-3 py-2.5 text-[0.95rem] leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">
              {answer}
            </p>
            <Separator className="my-5" />
            <EvaluationView evaluation={evaluation} />
          </>
        ) : (
          <form onSubmit={onSubmit} className="space-y-3">
            <Label htmlFor={answerId}>내 답안</Label>
            <Textarea
              id={answerId}
              rows={7}
              maxLength={10000}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              readOnly={busy}
              aria-describedby={hintId}
              className="min-h-40 text-base leading-relaxed"
            />
            <div className="flex flex-wrap items-center gap-3">
              <p id={hintId} className="text-xs text-muted-foreground">
                AI가 정확성·완전성·논리성·기술적 타당성·응용력을 평가합니다
              </p>
              <Button type="submit" size="lg" className="ml-auto" disabled={busy || answer.trim() === ""}>
                {busy ? <SpinnerIcon className="animate-spin" aria-hidden /> : <PaperPlaneRightIcon aria-hidden />}
                {busy ? "평가하는 중…" : "답안 제출"}
              </Button>
            </div>
            {busy && <EvaluationSkeleton />}
            {error && (
              <Alert variant="destructive">
                <WarningCircleIcon aria-hidden />
                <AlertTitle>평가하지 못했습니다</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function EvaluationSkeleton() {
  return (
    <div className="space-y-3 pt-2" aria-hidden>
      <Skeleton className="h-9 w-28" />
      <div className="grid gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-6" />
        ))}
      </div>
    </div>
  );
}
