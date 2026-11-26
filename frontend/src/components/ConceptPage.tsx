import { lazy, Suspense, useEffect, useState } from "react";
import { ArrowLeftIcon, ArrowSquareOutIcon, CardsIcon, CopyIcon, FlaskIcon, PlayIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";
import { api, ApiError, errorMessage, type ConceptDetail, type ConceptHistory, type ConceptSource } from "@/api";
import { elapsed, LEVEL_LABELS, StatusBadge } from "@/components/LabRun";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatKst } from "@/lib/format";

// Markdown 렌더러(react-markdown·remark-gfm)는 이 화면에서만 쓰므로 따로 불러온다
const Markdown = lazy(() => import("@/components/Markdown").then((m) => ({ default: m.Markdown })));
const RATINGS: Record<number, string> = { 1: "Again", 2: "Hard", 3: "Good", 4: "Easy" };
const RECENT_RUNS = 5;

// /concepts/:id: 개념 하나 (읽기 전용, 설계서 §E-2). 복습 상태·평가·실습 이력은 기록에서 계산한 값이다
export function ConceptPage() {
  const { id = "" } = useParams();
  const [concept, setConcept] = useState<ConceptDetail | null>(null);
  const [history, setHistory] = useState<ConceptHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setConcept(null);
    setHistory(null);
    setError(null);
    Promise.all([api.concept(id), api.conceptHistory(id)]).then(
      ([c, h]) => {
        setConcept(c);
        setHistory(h);
      },
      (e) => setError(e instanceof ApiError && e.status === 404 ? `개념 ${id}이(가) 없습니다.` : errorMessage(e)),
    );
  }, [id]);

  return (
    <div className="space-y-6">
      <Button variant="ghost" asChild className="-ml-2.5">
        <Link to="/concepts"><ArrowLeftIcon aria-hidden /> 개념 목록</Link>
      </Button>

      {error && (
        <Alert variant="destructive">
          <WarningCircleIcon aria-hidden />
          <AlertTitle>개념을 불러오지 못했습니다</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {!concept || !history ? (
        !error && <Skeleton className="h-64 rounded-xl" aria-label="불러오는 중" />
      ) : (
        <>
          <Header concept={concept} />
          <Cards history={history} />
          <Labs history={history} />
          <Body key={concept.id} concept={concept} />
        </>
      )}
    </div>
  );
}

// 본문은 Markdown으로 그리고, "원본"을 누르면 원본을 그대로 보여 준다
// (Markdown 개념은 개념 폴더의 파일 전체, Notion 개념은 가져와 저장한 본문과 Notion 링크)
function Body({ concept }: { concept: ConceptDetail }) {
  const [view, setView] = useState<"rendered" | "source">("rendered");
  const [source, setSource] = useState<ConceptSource | null>(null);
  const [error, setError] = useState<string | null>(null);

  function showSource() {
    setView("source");
    if (!source) api.conceptSource(concept.id).then(setSource, (e) => setError(errorMessage(e)));
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("원본을 복사했습니다");
    } catch {
      toast.error("복사하지 못했습니다. 직접 선택해 복사하세요.");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{view === "rendered" ? "본문" : "원본"}</CardTitle>
        <div role="group" aria-label="본문 보기" className="flex gap-1">
          <Button size="sm" variant={view === "rendered" ? "default" : "outline"} aria-pressed={view === "rendered"}
            onClick={() => setView("rendered")}>본문</Button>
          <Button size="sm" variant={view === "source" ? "default" : "outline"} aria-pressed={view === "source"}
            onClick={showSource}>원본</Button>
        </div>
      </CardHeader>
      <CardContent>
        {view === "rendered" ? (
          <Suspense fallback={<Skeleton className="h-40" aria-label="본문 불러오는 중" />}>
            <Markdown text={concept.content} />
          </Suspense>
        ) : error ? (
          <Alert variant="destructive">
            <WarningCircleIcon aria-hidden />
            <AlertTitle>원본을 열지 못했습니다</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : !source ? (
          <Skeleton className="h-40" aria-label="원본 불러오는 중" />
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {source.source_type === "markdown" ? (
                <span>개념 폴더의 <code className="rounded bg-muted px-1 py-0.5 font-mono text-foreground">{source.path}</code> 파일 그대로입니다</span>
              ) : (
                <>
                  <span>Notion에서 가져와 저장한 본문(Markdown)입니다.</span>
                  <a href={source.url!} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline">
                    Notion에서 열기 <ArrowSquareOutIcon className="size-3.5" aria-hidden />
                  </a>
                </>
              )}
              <Button variant="outline" size="sm" className="ml-auto" onClick={() => copy(source.text)}>
                <CopyIcon aria-hidden /> 복사
              </Button>
            </div>
            <pre aria-label="원본" className="max-h-[40rem] overflow-auto rounded-md bg-muted p-3 font-mono text-[0.82rem] leading-relaxed whitespace-pre-wrap">
              {source.text}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Header({ concept: c }: { concept: ConceptDetail }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-mono">{c.id}</Badge>
        {c.category && <Badge variant="outline">{c.category}</Badge>}
        {c.difficulty !== null && <Badge variant="outline">난이도 {c.difficulty}</Badge>}
        {c.archived && <Badge variant="destructive">보관됨</Badge>}
      </div>
      <h1 className="text-2xl font-semibold tracking-tight">{c.title}</h1>
      {c.keywords.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {c.keywords.map((k) => <Badge key={k} variant="secondary" className="font-normal">{k}</Badge>)}
        </div>
      )}
      <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]">
        <ConceptLinks label="선수 개념" ids={c.prerequisites} />
        <ConceptLinks label="연관 개념" ids={c.related} />
        <dt className="text-muted-foreground">원본</dt>
        <dd className="min-w-0 break-all">
          {c.source_type === "notion" ? "Notion" : <span className="font-mono text-[0.85em]">{c.source_ref}</span>}
          <span className="text-muted-foreground"> · 고치려면 원본을 고친 뒤 동기화하세요</span>
        </dd>
      </dl>
    </div>
  );
}

function ConceptLinks({ label, ids }: { label: string; ids: string[] }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="flex flex-wrap gap-x-2">
        {ids.length === 0 ? <span className="text-muted-foreground">없음</span> : ids.map((i) => (
          <Link key={i} to={`/concepts/${encodeURIComponent(i)}`} className="font-mono text-primary underline-offset-2 hover:underline">{i}</Link>
        ))}
      </dd>
    </>
  );
}

function Cards({ history }: { history: ConceptHistory }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><CardsIcon aria-hidden />카드 {history.cards.length}장</CardTitle>
      </CardHeader>
      <CardContent>
        {history.cards.length === 0 ? (
          <p className="text-sm text-muted-foreground">카드가 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">질문</th>
                  <th className="px-3 py-2 font-medium whitespace-nowrap">복습</th>
                  <th className="px-3 py-2 font-medium whitespace-nowrap">마지막 등급</th>
                  <th className="px-3 py-2 font-medium whitespace-nowrap">최근 평가</th>
                  <th className="py-2 pl-3 font-medium whitespace-nowrap">다음 복습</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {history.cards.map((c) => (
                  <tr key={c.card_id} className="align-top">
                    <td className="py-2.5 pr-3 leading-relaxed">{c.question}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap tabular-nums">{c.reviews}번</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{c.last_rating ? RATINGS[c.last_rating] : "—"}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap tabular-nums">{c.last_score !== null ? `${c.last_score}점` : "—"}</td>
                    <td className="py-2.5 pl-3 whitespace-nowrap">
                      {new Date(c.due_at).getTime() <= Date.now() ? "지금" : formatKst(c.due_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// 연결된 실습과 실행 이력. 하나의 점수로 합치지 않고 그대로 보여 준다 (§D-2)
function Labs({ history }: { history: ConceptHistory }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><FlaskIcon aria-hidden />실습</CardTitle>
      </CardHeader>
      <CardContent>
        {history.labs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            연결된 실습이 없습니다. 개념 원본의 labs(Notion "실습" 속성)나 시나리오의 concepts로 연결합니다.
          </p>
        ) : (
          <ul className="divide-y">
            {history.labs.map((lab) => (
              <li key={lab.scenario_id} className="space-y-2 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" className="font-mono">{lab.scenario_id}</Badge>
                  <span className="font-medium">{lab.title ?? "시나리오 파일이 없습니다"}</span>
                  {lab.title && (
                    <Button variant="outline" size="sm" asChild className="ml-auto">
                      <Link to={`/labs?start=${encodeURIComponent(lab.scenario_id)}`}><PlayIcon aria-hidden /> 실습 열기</Link>
                    </Button>
                  )}
                </div>
                {lab.runs.length === 0 ? (
                  <p className="text-sm text-muted-foreground">아직 해 보지 않았습니다</p>
                ) : (
                  <ul className="space-y-1 text-sm">
                    {lab.runs.slice(0, RECENT_RUNS).map((r) => (
                      <li key={r.run_id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <StatusBadge status={r.status} />
                        <span className="text-muted-foreground">
                          {[
                            LEVEL_LABELS[r.level] ?? r.level,
                            r.attempts_to_pass ? `${r.attempts_to_pass}번째 검증에 통과` : `시도 ${r.attempts}번`,
                            `힌트 ${r.hints_used}번`,
                            r.passed_at && `${elapsed(r.started_at, r.passed_at)} 걸림`,
                            formatKst(r.started_at),
                          ].filter(Boolean).join(" · ")}
                        </span>
                      </li>
                    ))}
                    {lab.runs.length > RECENT_RUNS && (
                      <li className="text-muted-foreground">그 전 실행 {lab.runs.length - RECENT_RUNS}번</li>
                    )}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
