import { useEffect, useState, type ReactNode } from "react";
import { FlaskIcon, PlayIcon, WarningCircleIcon, WarningIcon } from "@phosphor-icons/react";
import { Link } from "react-router";
import { api, errorMessage, type DashboardSummary, type DueCard, type Stages, type WeakConcept } from "@/api";
import { ColumnChart, Legend, Meter, StackedBar, TableView, TipRows, type Segment } from "@/components/DashboardCharts";
import { elapsed, StatusBadge } from "@/components/LabRun";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { todayKst } from "@/lib/format";

type Props = {
  cards: DueCard[] | null;              // 지금 복습할 카드. 학습 세션은 이 카드로만 연다 (D59)
  onStart: (pool: DueCard[]) => void;   // 학습 세션을 바로 연다
  onRefresh: () => void;                // 복습할 카드를 다시 불러온다
};

// 설계서 §E-3·§E-4. 서버가 저장된 기록에서 계산한 값을 보여 주기만 한다
export function DashboardPage({ cards, onStart, onRefresh }: Props) {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onRefresh(); // 지표와 시작 버튼의 카드 수가 같은 시점이 되게 한다
    api.dashboard().then(setData, (e) => setError(errorMessage(e)));
  }, []);

  const due = cards ?? [];
  const start: Start = {
    all: due,
    category: (category: string | null) => due.filter((c) => (c.category ?? "") === (category ?? "")),
    concept: (id: string) => due.filter((c) => c.concept_id === id),
    run: onStart,
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">{todayKst()}</p>
          <h1 className="text-2xl font-semibold tracking-tight">대시보드</h1>
        </div>
        {due.length > 0 && (
          <Button size="lg" onClick={() => onStart(due)}>
            <PlayIcon weight="fill" aria-hidden /> 학습 시작 · {due.length}장
          </Button>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <WarningCircleIcon aria-hidden />
          <AlertTitle>대시보드를 불러오지 못했습니다</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {data === null ? (
        !error && (
          <div className="space-y-3" aria-label="불러오는 중">
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-64 rounded-xl" />
          </div>
        )
      ) : (
        <>
          <Tiles today={data.today} />
          <VolumeCard days={data.reviews_by_day} />
          <ForecastCard days={data.due_by_day} />
          <ErrorRateCard data={data} start={start} />
          <StagesCard data={data} start={start} />
          <WeakCard data={data} start={start} />
          <LabsCard labs={data.labs} />
        </>
      )}
    </div>
  );
}

// 학습 세션을 열 카드 묶음 (지금 복습할 카드 중에서)
type Start = {
  all: DueCard[];
  category: (category: string | null) => DueCard[];
  concept: (id: string) => DueCard[];
  run: (pool: DueCard[]) => void;
};

// ---- 날짜 ("YYYY-MM-DD"는 KST 날짜, 시각은 +09:00) ----

const WEEKDAYS = "일월화수목금토";
function parts(date: string) {
  const [y, m, d] = date.split("-").map(Number);
  return { m, d, w: WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] };
}
const shortDate = (date: string) => `${parts(date).m}/${parts(date).d}`;
const longDate = (date: string) => `${parts(date).m}월 ${parts(date).d}일 (${parts(date).w})`;
const formatDay = (iso: string) =>
  new Date(iso).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric" });
const categoryLabel = (category: string | null) => category || "분류 없음";
const percent = (part: number, whole: number) => Math.round((part / whole) * 100);

// ---- 숫자 ----

function Tiles({ today }: { today: DashboardSummary["today"] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Tile label="지금 복습할 카드" value={today.due} unit="장"
        note={today.overdue > 0
          ? <span className="flex items-center gap-1 text-warning"><WarningIcon aria-hidden />밀린 복습 {today.overdue}장</span>
          : "밀린 복습 없음"} />
      <Tile label="오늘 복습한 카드" value={today.reviewed} unit="장" />
      <Tile label="연속 학습" value={today.streak_days} unit="일"
        note={today.streak_days > 0 && today.reviewed === 0 ? "오늘 복습하면 이어집니다" : undefined} />
      <Tile label="개념 · 카드" value={today.concepts} unit={`개 · ${today.cards}장`} />
    </div>
  );
}

function Tile({ label, value, unit, note }: { label: string; value: number; unit: string; note?: ReactNode }) {
  return (
    <Card className="gap-1 px-4 py-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p>
        <span className="text-3xl font-semibold tracking-tight">{value}</span>
        <span className="ml-1 text-sm text-muted-foreground">{unit}</span>
      </p>
      {note && <div className="text-xs text-muted-foreground">{note}</div>}
    </Card>
  );
}

// ---- 복습량 · 복습 예정 ----

// 오답(Again·Hard)을 기준선 쪽에 쌓아 날마다 높이를 비교할 수 있게 한다
const GRADES = [
  { key: "again", label: "Again", color: "bg-grade-again" },
  { key: "hard", label: "Hard", color: "bg-grade-hard" },
  { key: "good", label: "Good", color: "bg-grade-good" },
  { key: "easy", label: "Easy", color: "bg-grade-easy" },
] as const;

function VolumeCard({ days }: { days: DashboardSummary["reviews_by_day"] }) {
  const sums = GRADES.map((g) => days.reduce((sum, d) => sum + d[g.key], 0));
  const all = sums.reduce((a, b) => a + b, 0);
  return (
    <ChartCard title="복습량" description={`최근 4주 · ${all}번 복습. 빨간 부분이 오답(Again·Hard)입니다`}>
      {all === 0 ? <Empty>최근 4주 동안 복습 기록이 없습니다.</Empty> : (
        <>
          <Legend items={GRADES.map((g, i) => ({ label: g.label, color: g.color, value: String(sums[i]) }))} />
          <ColumnChart
            axis={days.map((d, i) => (i === days.length - 1 ? "오늘" : i % 7 === 0 ? shortDate(d.date) : null))}
            columns={days.map((d) => {
              const n = d.again + d.hard + d.good + d.easy;
              return {
                key: d.date,
                segments: GRADES.map((g) => ({ label: g.label, value: d[g.key], color: g.color })),
                label: `${longDate(d.date)} 복습 ${n}번: ${GRADES.map((g) => `${g.label} ${d[g.key]}`).join(", ")}`,
                tip: <TipRows title={`${longDate(d.date)} · ${n}번`}
                  rows={GRADES.map((g) => ({ label: g.label, value: String(d[g.key]), color: g.color })).reverse()} />,
              };
            })}
          />
          <TableView caption="날짜별 복습량" head={["날짜", ...GRADES.map((g) => g.label), "합계"]}
            rows={days.map((d) => [longDate(d.date), d.again, d.hard, d.good, d.easy, d.again + d.hard + d.good + d.easy])} />
        </>
      )}
    </ChartCard>
  );
}

function ForecastCard({ days }: { days: DashboardSummary["due_by_day"] }) {
  const label = (date: string, i: number) => (i === 0 ? "오늘" : i === 1 ? "내일" : `${shortDate(date)} (${parts(date).w})`);
  return (
    <ChartCard title="복습 예정" description="앞으로 7일 동안 날짜별로 복습할 카드. 오늘 칸에는 밀린 카드도 들어갑니다">
      {days.every((d) => d.cards === 0) ? <Empty>앞으로 7일 동안 복습할 카드가 없습니다.</Empty> : (
        <>
          <ColumnChart
            axis={days.map((d, i) => label(d.date, i))}
            columns={days.map((d, i) => ({
              key: d.date,
              segments: [{ label: "카드", value: d.cards, color: "bg-primary" }],
              cap: String(d.cards),
              label: `${longDate(d.date)} 복습 예정 ${d.cards}장`,
              tip: <TipRows title={longDate(d.date)} rows={[{ label: i === 0 ? "장 (밀린 카드 포함)" : "장", value: String(d.cards) }]} />,
            }))}
          />
          <TableView caption="날짜별 복습 예정" head={["날짜", "카드"]} rows={days.map((d) => [longDate(d.date), d.cards])} />
        </>
      )}
    </ChartCard>
  );
}

// ---- 오답률 (Again + Hard) ----

function ErrorRateCard({ data, start }: { data: DashboardSummary; start: Start }) {
  const weeks = data.errors_by_week;
  const weekLabel = (w: (typeof weeks)[number], i: number) =>
    i === weeks.length - 1 ? "최근 7일" : `${shortDate(w.start)}~${shortDate(w.end)}`;
  // 오답률이 높은 카테고리부터. 최근 기록이 없는 카테고리는 뒤로
  const categories = [...data.categories].sort((a, b) =>
    (b.reviews > 0 ? b.wrong / b.reviews : -1) - (a.reviews > 0 ? a.wrong / a.reviews : -1));
  return (
    <ChartCard title="오답률" description="복습 중 Again·Hard를 고른 비율">
      {weeks.every((w) => w.reviews === 0) ? <Empty>최근 4주 동안 복습 기록이 없습니다.</Empty> : (
        <section aria-label="주별 오답률" className="space-y-3">
          <h3 className="text-sm font-medium">주별 추이 (최근 4주)</h3>
          <ColumnChart max={100} unit="%" height={120}
            axis={weeks.map(weekLabel)}
            columns={weeks.map((w, i) => {
              const rate = w.reviews > 0 ? percent(w.wrong, w.reviews) : 0;
              return {
                key: w.start,
                segments: [{ label: "오답률", value: rate, color: "bg-grade-again" }],
                cap: w.reviews > 0 ? `${rate}%` : undefined,
                label: w.reviews > 0 ? `${weekLabel(w, i)} 오답률 ${rate}% (${w.reviews}번 중 ${w.wrong}번)` : `${weekLabel(w, i)} 복습 기록 없음`,
                tip: <TipRows title={`${longDate(w.start)} ~ ${longDate(w.end)}`}
                  rows={w.reviews > 0 ? [{ label: `오답 (${w.reviews}번 중 ${w.wrong}번)`, value: `${rate}%` }] : [{ label: "복습 기록 없음", value: "—" }]} />,
              };
            })}
          />
          <TableView caption="주별 오답률" head={["기간", "복습", "Again·Hard", "오답률"]}
            rows={weeks.map((w, i) => [weekLabel(w, i), w.reviews, w.wrong, w.reviews > 0 ? `${percent(w.wrong, w.reviews)}%` : "—"])} />
        </section>
      )}
      {categories.length > 0 && (
        <section aria-label="카테고리별 오답률" className="space-y-2 border-t pt-4">
          <h3 className="text-sm font-medium">카테고리별 (최근 {data.rules.recent_days}일)</h3>
          <ul className="divide-y">
            {categories.map((c) => (
              <li key={c.category ?? ""} className="flex items-center gap-3 py-1.5">
                <span className="w-28 shrink-0 truncate text-sm">{categoryLabel(c.category)}</span>
                {c.reviews > 0 ? (
                  <>
                    <Meter value={c.wrong / c.reviews} color="bg-grade-again"
                      label={`${categoryLabel(c.category)} 오답률 ${percent(c.wrong, c.reviews)}% (${c.reviews}번 중 ${c.wrong}번)`}
                      tip={<TipRows title={categoryLabel(c.category)} rows={[{ label: `오답 (${c.reviews}번 중 ${c.wrong}번)`, value: `${percent(c.wrong, c.reviews)}%` }]} />} />
                    <span className="w-24 shrink-0 text-right text-sm tabular-nums">
                      {percent(c.wrong, c.reviews)}% <span className="text-muted-foreground">({c.wrong}/{c.reviews})</span>
                    </span>
                  </>
                ) : (
                  <span className="flex-1 text-sm text-muted-foreground">기록 없음</span>
                )}
                <StartButton pool={start.category(c.category)} name={categoryLabel(c.category)} onStart={start.run} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </ChartCard>
  );
}

// ---- 학습 현황 (카드 단계) ----

// 왼쪽부터 많이 익힌 단계, 오른쪽 빈 트랙이 아직 복습하지 않은 카드
const STAGES = [
  { key: "mature", label: "익숙함", color: "bg-stage-mature" },
  { key: "review", label: "복습 중", color: "bg-stage-review" },
  { key: "learning", label: "학습 중", color: "bg-stage-learning" },
  { key: "new", label: "새 카드", color: "bg-muted-foreground/25" },
] as const;

const stageSegments = (s: Stages): Segment[] => STAGES.map((st) => ({ label: st.label, value: s[st.key], color: st.color }));
const stageCount = (s: Stages) => s.new + s.learning + s.review + s.mature;
const stageText = (s: Stages) => STAGES.map((st) => `${st.label} ${s[st.key]}`).join(", ");

function StagesCard({ data, start }: { data: DashboardSummary; start: Start }) {
  const all = data.stages;
  const row = (name: string, s: Stages) => (
    <>
      <StackedBar segments={stageSegments(s)} label={`${name} ${stageCount(s)}장: ${stageText(s)}`}
        tip={<TipRows title={`${name} · ${stageCount(s)}장`} rows={STAGES.map((st) => ({ label: st.label, value: String(s[st.key]), color: st.color }))} />} />
      <span className="w-14 shrink-0 text-right text-sm tabular-nums">{stageCount(s)}장</span>
    </>
  );
  return (
    <ChartCard title="학습 현황"
      description={`활성 카드의 FSRS 단계. 익숙함은 기억 안정성이 ${data.rules.mature_days}일 이상인 카드입니다`}>
      {stageCount(all) === 0 ? <Empty>카드가 없습니다. 개념을 추가하고 동기화하세요.</Empty> : (
        <>
          <Legend items={STAGES.map((st) => ({ label: st.label, color: st.color, value: String(all[st.key]) }))} />
          <ul className="divide-y">
            <li className="flex items-center gap-3 py-1.5">
              <span className="w-28 shrink-0 text-sm font-medium">전체</span>
              {row("전체", all)}
              <StartButton pool={start.all} name="전체" onStart={start.run} />
            </li>
            {data.categories.map((c) => (
              <li key={c.category ?? ""} className="flex items-center gap-3 py-1.5">
                <span className="w-28 shrink-0 truncate text-sm">{categoryLabel(c.category)}</span>
                {row(categoryLabel(c.category), c.stages)}
                <StartButton pool={start.category(c.category)} name={categoryLabel(c.category)} onStart={start.run} />
              </li>
            ))}
          </ul>
          <TableView caption="카테고리별 학습 현황" head={["카테고리", ...STAGES.map((st) => st.label), "합계"]}
            rows={[{ name: "전체", s: all }, ...data.categories.map((c) => ({ name: categoryLabel(c.category), s: c.stages }))].map(
              ({ name, s }) => [name, ...STAGES.map((st) => s[st.key]), stageCount(s)])} />
        </>
      )}
    </ChartCard>
  );
}

function StartButton({ pool, name, onStart }: { pool: DueCard[]; name: string; onStart: (pool: DueCard[]) => void }) {
  return (
    <Button variant="outline" size="sm" className="w-28 shrink-0" disabled={pool.length === 0} onClick={() => onStart(pool)}
      aria-label={pool.length > 0 ? `${name} 복습 시작 (${pool.length}장)` : `${name} 지금 복습할 카드 없음`}>
      {pool.length > 0 ? <><PlayIcon aria-hidden /> 복습 {pool.length}장</> : "복습할 카드 없음"}
    </Button>
  );
}

// ---- 취약 개념 (§E-4) ----

const RATING_LABELS: Record<number, string> = { 1: "Again", 2: "Hard" };

function signalText(signal: WeakConcept["signals"][number], w: WeakConcept) {
  if (signal === "forgot") return `잊음 · Again ${w.again}회`;
  if (signal === "struggled") return `힘들게 떠올림 · Again·Hard ${w.again + w.hard}회`;
  return `낮은 평가 · ${w.low_scores}회`;
}

function WeakCard({ data, start }: { data: DashboardSummary; start: Start }) {
  const r = data.rules;
  return (
    <ChartCard title="취약 개념"
      description={`최근 ${r.recent_days}일 동안 Again ${r.forgot}회 이상, Again·Hard ${r.struggled}회 이상, 원래 질문 평가 ${r.low_score}점 미만 ${r.low_score_count}회 이상 중 하나라도 걸린 개념입니다. 실력 점수가 아니라 다음에 복습할 곳을 고르는 참고입니다`}>
      {data.weak_concepts.length === 0 ? <Empty>기준에 걸린 개념이 없습니다.</Empty> : (
        <ul className="divide-y" aria-label="취약 개념 목록">
          {data.weak_concepts.map((w) => {
            const pool = start.concept(w.concept_id);
            return (
              <li key={w.concept_id} className="space-y-2 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" className="font-mono">{w.concept_id}</Badge>
                  <Link to={`/concepts/${encodeURIComponent(w.concept_id)}`} className="font-medium underline-offset-4 hover:underline">{w.title}</Link>
                  <span className="ml-auto">
                    {pool.length > 0 ? (
                      <Button size="sm" onClick={() => start.run(pool)} aria-label={`${w.title} 복습 시작 (${pool.length}장)`}>
                        <PlayIcon aria-hidden /> 복습 {pool.length}장
                      </Button>
                    ) : (
                      <span className="text-sm text-muted-foreground">{w.next_due_at ? `다음 복습 ${formatDay(w.next_due_at)}` : "복습할 카드 없음"}</span>
                    )}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {w.signals.map((s) => (
                    <Badge key={s} variant="outline"><WarningCircleIcon aria-hidden />{signalText(s, w)}</Badge>
                  ))}
                </div>
                <details className="text-sm">
                  <summary className="w-fit cursor-pointer text-muted-foreground select-none hover:text-foreground">
                    근거 {w.lapses.length + w.low_evaluations.length}건
                  </summary>
                  <ul className="mt-2 space-y-1.5">
                    {w.lapses.map((l, i) => (
                      <li key={`l${i}`}>
                        <span className="text-muted-foreground">{formatDay(l.reviewed_at)} · {RATING_LABELS[l.rating]}</span> {l.question}
                      </li>
                    ))}
                    {w.low_evaluations.map((e, i) => (
                      <li key={`e${i}`}>
                        <span className="text-muted-foreground">{formatDay(e.submitted_at)} · {e.score}점</span> {e.question}
                        {e.missing_points.length > 0 && (
                          <ul className="mt-0.5 list-disc pl-5 text-muted-foreground">
                            {e.missing_points.map((p) => <li key={p}>빠진 내용: {p}</li>)}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            );
          })}
        </ul>
      )}
    </ChartCard>
  );
}

// ---- 실습 ----

function LabsCard({ labs }: { labs: DashboardSummary["labs"] }) {
  return (
    <ChartCard title={<><FlaskIcon aria-hidden />실습</>} description="시나리오별 실행 수와 마지막 실행. 하나의 성공률로 합치지 않습니다">
      {labs.length === 0 ? <Empty>실습 시나리오가 없습니다.</Empty> : (
        <ul className="divide-y" aria-label="실습 이력">
          {labs.map((lab) => (
            <li key={lab.scenario_id} className="flex flex-wrap items-center gap-x-2 gap-y-1.5 py-2.5 first:pt-0 last:pb-0">
              <Badge variant="secondary" className="font-mono">{lab.scenario_id}</Badge>
              <span className="font-medium">{lab.title}</span>
              <span className="text-sm text-muted-foreground">{lab.runs > 0 ? `실행 ${lab.runs}번` : "아직 해 보지 않았습니다"}</span>
              {lab.last_run && (
                <span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  <StatusBadge status={lab.last_run.status} />
                  {[
                    lab.last_run.attempts_to_pass ? `${lab.last_run.attempts_to_pass}번째 검증에 통과` : `시도 ${lab.last_run.attempts}번`,
                    lab.last_run.passed_at && `${elapsed(lab.last_run.started_at, lab.last_run.passed_at)} 걸림`,
                  ].filter(Boolean).join(" · ")}
                </span>
              )}
              <Button variant="outline" size="sm" asChild className="ml-auto">
                <Link to={`/labs?start=${encodeURIComponent(lab.scenario_id)}`}><PlayIcon aria-hidden /> 실습 열기</Link>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </ChartCard>
  );
}

// ---- 공통 ----

function ChartCard({ title, description, children }: { title: ReactNode; description: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}
