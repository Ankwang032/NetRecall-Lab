import { CheckCircleIcon, FlaskIcon, WarningCircleIcon, XCircleIcon, type Icon } from "@phosphor-icons/react";
import type { Evaluation } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

type ScoreKey = "accuracy" | "completeness" | "logic" | "technical_validity" | "application";
const SCORES: [ScoreKey, string][] = [
  ["accuracy", "정확성"],
  ["completeness", "완전성"],
  ["logic", "논리성"],
  ["technical_validity", "기술적 타당성"],
  ["application", "응용력"],
];

// 색만으로 구분하지 않도록 글자(우수·보통·부족)를 같이 보여 준다
function grade(score: number) {
  if (score >= 85) return { label: "우수", className: "bg-success/10 text-success" };
  if (score >= 60) return { label: "보통", className: "bg-warning/10 text-warning" };
  return { label: "부족", className: "bg-destructive/10 text-destructive" };
}

export function EvaluationView({ evaluation: ev }: { evaluation: Evaluation }) {
  const g = grade(ev.score);
  return (
    <section aria-label="AI 평가" className="space-y-5">
      <div className="flex items-end gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">AI 평가</p>
          <p className="text-4xl font-semibold tracking-tight tabular-nums">
            {ev.score}
            <span className="text-base font-normal text-muted-foreground"> / 100</span>
          </p>
        </div>
        <Badge className={cn("mb-1.5", g.className)}>{g.label}</Badge>
      </div>

      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        {SCORES.map(([key, label]) => (
          <div key={key}>
            <div className="flex items-baseline justify-between text-sm">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-medium tabular-nums">{ev[key]}</dd>
            </div>
            <Progress value={ev[key]} aria-label={label} className="mt-1.5 h-1.5" />
          </div>
        ))}
      </dl>

      <Feedback icon={CheckCircleIcon} tone="text-success" title="잘한 점" items={ev.strengths} />
      <Feedback icon={WarningCircleIcon} tone="text-warning" title="빠진 내용" items={ev.missing_points} />
      <Feedback icon={XCircleIcon} tone="text-destructive" title="기술적 오류" items={ev.technical_errors} />

      {ev.recommended_lab && (
        <p className="flex items-center gap-2 text-sm">
          <FlaskIcon className="size-4 text-primary" aria-hidden />
          추천 실습
          <Badge variant="outline" className="font-mono">{ev.recommended_lab}</Badge>
        </p>
      )}
      <p className="text-xs text-muted-foreground">평가 모델 {ev.model}</p>
    </section>
  );
}

type FeedbackProps = { icon: Icon; tone: string; title: string; items: string[] };

function Feedback({ icon: IconComponent, tone, title, items }: FeedbackProps) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        <IconComponent weight="fill" className={cn("size-4", tone)} aria-hidden />
        {title}
      </h3>
      <ul className="mt-1.5 space-y-1 pl-5.5 text-[0.95rem] leading-relaxed">
        {items.map((item, i) => (
          <li key={i} className="list-disc marker:text-muted-foreground">{item}</li>
        ))}
      </ul>
    </div>
  );
}
