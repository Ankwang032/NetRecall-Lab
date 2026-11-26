import { useEffect, useState } from "react";
import { FlaskIcon, PlayIcon, SpinnerIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { api, errorMessage, type LabLevel, type LabList, type LabRun, type LabScenario } from "@/api";
import { isLive, LabRunView, LEVEL_LABELS, StatusBadge } from "@/components/LabRun";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { formatKst } from "@/lib/format";
import { cn } from "@/lib/utils";

const LEVELS: { value: LabLevel; description: string }[] = [
  { value: "easy", description: "검사마다 힌트 3단계까지" },
  { value: "normal", description: "검사마다 힌트 2단계까지" },
  { value: "hard", description: "힌트 없음. 검사 목록과 검사별 결과는 끝낼 때 보여 주고, 검증하면 통과 개수만 알려 줍니다" },
];
const TYPE_LABELS: Record<string, string> = { build: "구성", troubleshoot: "장애 해결" };

// /labs: 실습 목록과 진행 중인 실행. ?start=LAB-002 로 열면(답안 평가의 추천 실습) 그 실습의 시작 창을 연다
export function LabsPage() {
  const [params, setParams] = useSearchParams();
  const [list, setList] = useState<LabList | null>(null);
  const [run, setRun] = useState<LabRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<LabScenario | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadList() {
    setList(await api.labs());
  }

  useEffect(() => {
    const wanted = params.get("start");
    (async () => {
      try {
        // 시간 제한이 지난 실행은 서버가 요청 때 정리한다. 같은 실행을 두 요청이 같이 정리하지 않게 차례로 부른다
        const current = await api.currentRun();
        const labs = await api.labs();
        setRun(current);
        setList(labs);
        if (wanted) {
          const scenario = labs.scenarios.find((s) => s.id === wanted);
          if (!scenario) setNotice(`추천 실습 ${wanted}을(를) 찾지 못했습니다.`);
          else if (current) setNotice(`진행 중인 실습이 있어 추천 실습 ${wanted}을(를) 바로 시작하지 않았습니다. 지금 실습을 끝낸 뒤 시작하세요.`);
          else setStarting(scenario);
          setParams({}, { replace: true });
        }
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
  }, []); // 처음 열 때 한 번만

  function changed(next: LabRun) {
    setRun(next);
    if (!isLive(next)) loadList().catch(() => {});
  }

  async function start(scenarioId: string, level: LabLevel) {
    const next = await api.startLab(scenarioId, level);
    setRun(next);
    setNotice(null);
    toast.success("실습 환경을 배포했습니다", { description: "노드 접속 명령을 자기 터미널에서 실행하세요." });
    loadList().catch(() => {});
  }

  async function restart(old: LabRun) {
    if (isLive(old)) changed(await api.finishLab(old.run_id));
    await start(old.scenario_id, old.level);
  }

  return (
    <div className="space-y-6">
      {notice && (
        <Alert>
          <FlaskIcon aria-hidden />
          <AlertTitle>추천 실습</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <WarningCircleIcon aria-hidden />
          <AlertTitle>실습을 불러오지 못했습니다</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {run ? (
        <LabRunView key={run.run_id} run={run} onChange={changed} onRestart={restart} onClose={() => setRun(null)} />
      ) : (
        <ScenarioList list={list} loading={!list && !error} onStart={setStarting} />
      )}

      <StartDialog scenario={starting} onClose={() => setStarting(null)} onStart={start} />
    </div>
  );
}

function ScenarioList({ list, loading, onStart }: { list: LabList | null; loading: boolean; onStart: (s: LabScenario) => void }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">실습</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          빈 토폴로지를 배포하면 노드에 직접 접속해 설정하고, 검증으로 결과를 확인합니다. 한 번에 하나만 진행합니다.
        </p>
      </div>

      {list && list.errors.length > 0 && (
        <Alert variant="destructive">
          <WarningCircleIcon aria-hidden />
          <AlertTitle>읽지 못한 시나리오 {list.errors.length}개</AlertTitle>
          <AlertDescription>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {list.errors.map((e) => (
                <li key={e.scenario}><span className="font-mono">{e.scenario}</span>: {e.message}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {loading ? (
        <div className="space-y-3" aria-label="불러오는 중">
          {Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
      ) : list && list.scenarios.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">실습 시나리오가 없습니다.</CardContent></Card>
      ) : (
        <ul className="space-y-3">
          {list?.scenarios.map((s) => (
            <li key={s.id}>
              <Card className="py-4">
                <CardContent className="flex flex-wrap items-center gap-4">
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary" className="font-mono">{s.id}</Badge>
                      <h2 className="font-medium">{s.title}</h2>
                    </div>
                    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                      <span>{TYPE_LABELS[s.type] ?? s.type}</span>
                      <span>시간 제한 {s.time_limit_minutes}분</span>
                      <span className="flex gap-1">
                        개념 {s.concepts.map((c) => <Badge key={c} variant="outline" className="font-mono">{c}</Badge>)}
                      </span>
                    </p>
                    <LastRun run={s.last_run} />
                  </div>
                  <Button onClick={() => onStart(s)}>
                    <PlayIcon weight="fill" aria-hidden /> 시작
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LastRun({ run }: { run: LabScenario["last_run"] }) {
  if (!run) return <p className="text-sm text-muted-foreground">아직 해 보지 않았습니다</p>;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <span className="text-muted-foreground">마지막</span>
      <StatusBadge status={run.status} />
      <span className="text-muted-foreground">
        {LEVEL_LABELS[run.level] ?? run.level} · 시도 {run.attempts}번 · 힌트 {run.hints_used}번 · {formatKst(run.started_at)}
      </span>
    </p>
  );
}

type StartProps = {
  scenario: LabScenario | null;
  onClose: () => void;
  onStart: (scenarioId: string, level: LabLevel) => Promise<void>;
};

function StartDialog({ scenario, onClose, onStart }: StartProps) {
  const [level, setLevel] = useState<LabLevel>("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!scenario) return;
    setBusy(true);
    setError(null);
    try {
      await onStart(scenario.id, level);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={scenario !== null} onOpenChange={(open) => !open && !busy && (setError(null), onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{scenario?.id} 시작</DialogTitle>
          <DialogDescription>
            {scenario?.title}. 주소 대역은 실행마다 새로 정해집니다. 배포에 몇 초에서 수십 초가 걸립니다.
          </DialogDescription>
        </DialogHeader>
        <fieldset className="space-y-2" disabled={busy}>
          <legend className="mb-2 text-sm font-medium">도움 수준</legend>
          {LEVELS.map((l) => (
            <label key={l.value}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors has-focus-visible:ring-3 has-focus-visible:ring-ring/50",
                level === l.value ? "border-primary bg-accent/50" : "hover:bg-muted/60",
              )}>
              <input type="radio" name="level" value={l.value} checked={level === l.value}
                onChange={() => setLevel(l.value)} className="mt-1 accent-primary" />
              <span>
                <span className="font-medium">{LEVEL_LABELS[l.value]}</span>
                {l.value === "normal" && <span className="text-muted-foreground"> (기본)</span>}
                <span className="block text-sm text-muted-foreground">{l.description}</span>
              </span>
            </label>
          ))}
        </fieldset>
        {error && (
          <Alert variant="destructive">
            <WarningCircleIcon aria-hidden />
            <AlertTitle>시작하지 못했습니다</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <DialogClose asChild><Button variant="outline" disabled={busy}>취소</Button></DialogClose>
          <Button onClick={submit} disabled={busy}>
            {busy ? <SpinnerIcon className="animate-spin" aria-hidden /> : <PlayIcon weight="fill" aria-hidden />}
            {busy ? "배포 중…" : "시작"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
