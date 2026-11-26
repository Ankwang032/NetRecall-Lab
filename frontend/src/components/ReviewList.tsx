import { CaretRightIcon, CheckCircleIcon, FilePlusIcon, PlayIcon, WarningCircleIcon } from "@phosphor-icons/react";
import type { DueCard, SyncResponse } from "@/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { FilterButton } from "@/components/FilterButton";
import { todayKst } from "@/lib/format";

type Props = {
  cards: DueCard[] | null;
  topic: string | null; // 고른 카테고리. null이면 전체, ""는 카테고리 없는 개념
  onTopic: (topic: string | null) => void;
  error: string | null;
  syncIssues: SyncResponse | null;
  onStart: (pool: DueCard[], first?: DueCard) => void; // pool을 first부터 차례로 학습한다
  onUpload: () => void;
};

export function ReviewList({ cards, topic, onTopic, error, syncIssues, onStart, onUpload }: Props) {
  const topics = countTopics(cards ?? []);
  // 고른 주제의 카드를 다 복습해 목록에서 사라졌으면 전체를 보여 준다
  const active = topic !== null && topics.some((t) => t.key === topic) ? topic : null;
  const visible = (cards ?? []).filter((c) => active === null || (c.category ?? "") === active);
  const groups = groupByConcept(visible);
  const activeLabel = topics.find((t) => t.key === active)?.label;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">{todayKst()}</p>
          <h1 className="text-2xl font-semibold tracking-tight">오늘의 복습</h1>
          {visible.length > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              {activeLabel && `${activeLabel} · `}카드 {visible.length}장 · 개념 {groups.length}개
            </p>
          )}
        </div>
        {visible.length > 0 && (
          <Button size="lg" onClick={() => onStart(visible)}>
            <PlayIcon weight="fill" aria-hidden /> {activeLabel ? `${activeLabel} 학습 시작` : "학습 시작"}
          </Button>
        )}
      </div>

      {topics.length > 1 && (
        <div role="group" aria-label="주제" className="flex flex-wrap gap-1.5">
          <FilterButton label="전체" count={cards?.length ?? 0} pressed={active === null} onClick={() => onTopic(null)} />
          {topics.map((t) => (
            <FilterButton key={t.key} label={t.label} count={t.count} pressed={active === t.key} onClick={() => onTopic(t.key)} />
          ))}
        </div>
      )}

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
              <div className="flex items-center gap-2 border-b px-4 py-2">
                <Badge variant="secondary" className="font-mono">{conceptId}</Badge>
                <h2 className="font-medium">{title}</h2>
                <span className="ml-auto text-xs text-muted-foreground">{group.length}장</span>
                <Button variant="ghost" size="sm" onClick={() => onStart(group)} aria-label={`이 개념만 학습 (${title})`}>
                  <PlayIcon aria-hidden /> 이 개념만
                </Button>
              </div>
              <ul className="divide-y">
                {group.map((card) => (
                  <li key={card.card_id}>
                    <button
                      onClick={() => onStart(visible, card)}
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

// 카테고리별 카드 수. 많은 순
function countTopics(cards: DueCard[]) {
  const counts = new Map<string, number>();
  for (const card of cards) counts.set(card.category ?? "", (counts.get(card.category ?? "") ?? 0) + 1);
  return [...counts]
    .map(([key, count]) => ({ key, label: key || "분류 없음", count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "ko"));
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
