import { useEffect, useState } from "react";
import { CaretRightIcon, MagnifyingGlassIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage, type ConceptSummary } from "@/api";
import { FilterButton } from "@/components/FilterButton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { formatKst } from "@/lib/format";

// /concepts: 개념 목록 (읽기 전용, 설계서 §E-2). 검색어·카테고리·보관 포함 여부는 주소에 둬서 뒤로 가기로 돌아와도 남는다
export function ConceptsPage() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const category = params.get("category"); // null이면 전체, ""는 카테고리 없음
  const archived = params.get("archived") === "1";
  const [concepts, setConcepts] = useState<ConceptSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setConcepts(null);
    api.concepts(archived).then(setConcepts, (e) => setError(errorMessage(e)));
  }, [archived]);

  function update(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  }

  const all = concepts ?? [];
  const categories = countCategories(all);
  const active = category !== null && categories.some((c) => c.key === category) ? category : null;
  const words = query.trim().toLowerCase();
  const visible = all.filter(
    (c) =>
      (active === null || (c.category ?? "") === active) &&
      (!words || [c.id, c.title, ...c.keywords].some((t) => t.toLowerCase().includes(words))),
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">개념</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          읽기 전용입니다. 개념은 원본(.md 파일·Notion)에서 고친 뒤 동기화하세요.
        </p>
      </div>

      <div className="space-y-3">
        <div className="relative">
          <MagnifyingGlassIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input type="search" value={query} onChange={(e) => update("q", e.target.value || null)}
            placeholder="제목·키워드·id로 찾기" aria-label="개념 찾기" className="h-10 pl-9" />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {categories.length > 1 && (
            <div role="group" aria-label="카테고리" className="flex flex-wrap gap-1.5">
              <FilterButton label="전체" count={all.length} pressed={active === null} onClick={() => update("category", null)} />
              {categories.map((c) => (
                <FilterButton key={c.key} label={c.label} count={c.count} pressed={active === c.key}
                  onClick={() => update("category", c.key)} />
              ))}
            </div>
          )}
          <div className="ml-auto flex items-center gap-2">
            <Checkbox id="show-archived" checked={archived} onCheckedChange={(v) => update("archived", v === true ? "1" : null)} />
            <Label htmlFor="show-archived" className="text-sm font-normal text-muted-foreground">보관된 개념도 보기</Label>
          </div>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <WarningCircleIcon aria-hidden />
          <AlertTitle>개념을 불러오지 못했습니다</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {concepts === null ? (
        !error && (
          <div className="space-y-2" aria-label="불러오는 중">
            {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
          </div>
        )
      ) : visible.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          {all.length === 0 ? "개념이 없습니다. 개념 파일을 추가하거나 동기화하세요." : "찾는 개념이 없습니다."}
        </p>
      ) : (
        <Card className="gap-0 py-0">
          <ul className="divide-y" aria-label="개념 목록">
            {visible.map((c) => (
              <li key={c.id}>
                <Link to={`/concepts/${encodeURIComponent(c.id)}`}
                  className="flex items-center gap-3 px-4 py-3 transition-colors outline-none hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset">
                  <Badge variant="secondary" className="shrink-0 font-mono">{c.id}</Badge>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {c.title}
                      {c.archived && <Badge variant="outline" className="ml-2 align-middle">보관됨</Badge>}
                    </p>
                    <p className="truncate text-sm text-muted-foreground">
                      {[c.category ?? "분류 없음", ...c.keywords.slice(0, 4)].join(" · ")}
                    </p>
                  </div>
                  <p className="hidden shrink-0 text-right text-sm text-muted-foreground sm:block">
                    카드 {c.card_count}장
                    <span className="block text-xs">{nextDue(c.next_due_at)}</span>
                  </p>
                  <CaretRightIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

export function nextDue(at: string | null) {
  if (!at) return "복습할 카드 없음";
  return new Date(at).getTime() <= Date.now() ? "지금 복습할 때" : `다음 복습 ${formatKst(at)}`;
}

function countCategories(concepts: ConceptSummary[]) {
  const counts = new Map<string, number>();
  for (const c of concepts) counts.set(c.category ?? "", (counts.get(c.category ?? "") ?? 0) + 1);
  return [...counts]
    .map(([key, count]) => ({ key, label: key || "분류 없음", count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "ko"));
}
