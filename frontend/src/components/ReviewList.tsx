import { CaretRightIcon, CheckCircleIcon, FilePlusIcon, PlayIcon, WarningCircleIcon } from "@phosphor-icons/react";
import type { DueCard, SyncResponse } from "@/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { todayKst } from "@/lib/format";

type Props = {
  cards: DueCard[] | null;
  error: string | null;
  syncIssues: SyncResponse | null;
  onStart: (card: DueCard) => void;
  onUpload: () => void;
};

export function ReviewList({ cards, error, syncIssues, onStart, onUpload }: Props) {
  const groups = groupByConcept(cards ?? []);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">{todayKst()}</p>
          <h1 className="text-2xl font-semibold tracking-tight">오늘의 복습</h1>
          {cards && cards.length > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              카드 {cards.length}장 · 개념 {groups.length}개
            </p>
          )}
        </div>
        {cards && cards.length > 0 && (
          <Button size="lg" onClick={() => onStart(cards[0])}>
            <PlayIcon weight="fill" aria-hidden /> 학습 시작
          </Button>
        )}
      </div>

      {syncIssues && <SyncIssues result={syncIssues} />}
      {error && (
        <Alert variant="destructive">
          <WarningCircleIcon aria-hidden />
          <AlertTitle>복습할 카드를 불러오지 못했습니다</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {cards === null ? (
        !error && <ListSkeleton />
      ) : cards.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <CheckCircleIcon weight="duotone" className="size-10 text-primary" aria-hidden />
            <div>
              <p className="font-medium">지금 복습할 카드가 없습니다</p>
              <p className="mt-1 text-sm text-muted-foreground">
                새 개념 파일을 추가하거나, 개념 폴더의 파일을 고쳤다면 동기화하세요.
              </p>
            </div>
            <Button variant="outline" onClick={onUpload}>
              <FilePlusIcon aria-hidden /> 개념 추가
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {groups.map(({ conceptId, title, cards: group }) => (
            <Card key={conceptId} className="gap-0 py-0">
              <div className="flex items-center gap-2 border-b px-4 py-3">
                <Badge variant="secondary" className="font-mono">{conceptId}</Badge>
                <h2 className="font-medium">{title}</h2>
                <span className="ml-auto text-xs text-muted-foreground">{group.length}장</span>
              </div>
              <ul className="divide-y">
                {group.map((card) => (
                  <li key={card.card_id}>
                    <button
                      onClick={() => onStart(card)}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left text-[0.95rem] leading-relaxed transition-colors outline-none hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset"
                    >
                      <span className="flex-1">{card.question}</span>
                      <CaretRightIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function groupByConcept(cards: DueCard[]) {
  const groups = new Map<string, { conceptId: string; title: string; cards: DueCard[] }>();
  for (const card of cards) {
    const group = groups.get(card.concept_id) ?? { conceptId: card.concept_id, title: card.concept_title, cards: [] };
    group.cards.push(card);
    groups.set(card.concept_id, group);
  }
  return [...groups.values()];
}

function SyncIssues({ result }: { result: SyncResponse }) {
  return (
    <Alert variant={result.errors.length > 0 ? "destructive" : "default"}>
      <WarningCircleIcon aria-hidden />
      <AlertTitle>
        {result.errors.length > 0 ? `동기화하지 못한 항목 ${result.errors.length}개` : "동기화하며 확인할 내용"}
      </AlertTitle>
      <AlertDescription>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {result.errors.map((e, i) => (
            <li key={i}>
              <span className="font-mono">{e.source_ref}</span>: {e.message}
            </li>
          ))}
          {result.warnings.map((w, i) => (
            <li key={`warn-${i}`} className="text-warning">
              <span className="font-mono">{w.source_ref}</span>: {w.message}
            </li>
          ))}
          {result.dangling_refs.map((r, i) => (
            <li key={`ref-${i}`}>
              <span className="font-mono">{r.concept_id}</span> → <span className="font-mono">{r.ref}</span> (없는 개념)
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3" aria-label="불러오는 중">
      {Array.from({ length: 2 }, (_, i) => (
        <Skeleton key={i} className="h-36 rounded-xl" />
      ))}
    </div>
  );
}
