import { useEffect, useRef, useState } from "react";
import {
  ArrowCounterClockwiseIcon, CheckCircleIcon, CircleDashedIcon, ClockCountdownIcon, CopyIcon, LightbulbIcon,
  ListChecksIcon, SpinnerIcon, StopCircleIcon, TerminalWindowIcon, WarningCircleIcon, XCircleIcon,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { api, ApiError, errorMessage, type LabResult, type LabRun } from "@/api";
import { LabTopology } from "@/components/LabTopology";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { formatKst } from "@/lib/format";
import { cn } from "@/lib/utils";

export const LEVEL_LABELS: Record<string, string> = { easy: "쉬움", normal: "보통", hard: "어려움" };
export const STATUS_LABELS: Record<string, string> = {
  deploying: "배포 중",
  active: "진행 중",
  passed: "통과",
  abandoned: "포기",
  expired: "시간 초과",
  deploy_failed: "배포 실패",
};
const KIND_LABELS: Record<string, string> = { host: "Linux", router: "FRRouting" };

// 환경이 남아 있어 설정·검증할 수 있는 실행
export const isLive = (run: LabRun) => run.finished_at === null && ["active", "passed"].includes(run.status);

type Props = {
  run: LabRun;
  onChange: (run: LabRun) => void;
  onRestart: (run: LabRun) => Promise<void>; // 지금 실행을 끝내고 같은 실습·같은 도움 수준으로 새로 시작
  onClose: () => void; // 끝난 실행을 닫고 목록으로
};

export function LabRunView({ run, onChange, onRestart, onClose }: Props) {
  const live = isLive(run);
  const [busy, setBusy] = useState<"verify" | "finish" | "restart" | null>(null);
  const [confirm, setConfirm] = useState<"finish" | "restart" | null>(null);

  async function refresh() {
    onChange(await api.labRun(run.run_id));
  }

  // 시간 제한이 지났거나 다른 곳에서 끝낸 실행(409)이면 상태를 다시 읽는다
  async function guarded(action: () => Promise<void>, failTitle: string) {
    try {
      await action();
    } catch (e) {
      toast.error(failTitle, { description: errorMessage(e) });
      if (e instanceof ApiError && e.status === 409) await refresh().catch(() => {});
    }
  }

  async function verify() {
    setBusy("verify");
    await guarded(async () => {
      const attempt = await api.verifyLab(run.run_id);
      await refresh();
      if (attempt.passed) toast.success("모든 검사를 통과했습니다", { description: "끝내기를 누르면 실습 환경을 지웁니다." });
    }, "검증하지 못했습니다");
    setBusy(null);
  }

  async function finish() {
    setConfirm(null);
    setBusy("finish");
    await guarded(async () => onChange(await api.finishLab(run.run_id)), "끝내지 못했습니다");
    setBusy(null);
  }

  async function restart() {
    setConfirm(null);
    setBusy("restart");
    await guarded(() => onRestart(run), "다시 시작하지 못했습니다");
    setBusy(null);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="font-mono">{run.scenario_id}</Badge>
            <StatusBadge status={run.status} />
            <Badge variant="outline">도움 수준 {LEVEL_LABELS[run.level] ?? run.level}</Badge>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{run.title}</h1>
          <p className="text-sm text-muted-foreground">
            시도 {run.attempts}번 · 힌트 {run.hints_used}번
            {run.passed_at && ` · ${elapsed(run.started_at, run.passed_at)} 만에 통과`}
          </p>
        </div>
        {live ? (
          <div className="flex flex-col items-end gap-2">
            <Countdown expiresAt={run.expires_at} onExpired={() => refresh().catch(() => {})} />
            <div className="flex gap-1.5">
              <Button variant="outline" onClick={() => setConfirm("restart")} disabled={busy !== null}>
                {busy === "restart" ? <SpinnerIcon className="animate-spin" aria-hidden /> : <ArrowCounterClockwiseIcon aria-hidden />}
                처음부터 다시
              </Button>
              <Button variant="destructive" onClick={() => setConfirm("finish")} disabled={busy !== null}>
                {busy === "finish" ? <SpinnerIcon className="animate-spin" aria-hidden /> : <StopCircleIcon aria-hidden />}
                끝내기
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-1.5">
            <Button variant="outline" onClick={onClose}>목록으로</Button>
            <Button onClick={restart} disabled={busy !== null}>
              {busy === "restart" ? <SpinnerIcon className="animate-spin" aria-hidden /> : <ArrowCounterClockwiseIcon aria-hidden />}
              다시 하기
            </Button>
          </div>
        )}
      </div>

      {!live && <Finished run={run} />}

      <Card>
        <CardHeader><CardTitle>목표</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="leading-relaxed"><Inline text={run.goal} /></p>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {Object.entries(run.networks).map(([name, cidr]) => (
              <div key={name} className="flex gap-2">
                <dt className="text-muted-foreground">대역 {name}</dt>
                <dd className="font-mono">{cidr}</dd>
              </div>
            ))}
          </dl>
          <div className="overflow-x-auto rounded-lg border bg-background p-3">
            <LabTopology nodes={run.nodes} links={run.links} addresses={run.addresses} />
          </div>
        </CardContent>
      </Card>

      {live && <Connect nodes={run.nodes} />}

      <Checks run={run} live={live} onChange={onChange} verifying={busy === "verify"} onVerify={verify} />

      <Dialog open={confirm === "finish"} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>실습을 끝낼까요?</DialogTitle>
            <DialogDescription>
              실습 환경이 지워집니다. 마지막 설정은 기록에 남습니다.
              {run.status !== "passed" && " 아직 통과하지 못해 포기로 기록됩니다."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild><Button variant="outline">취소</Button></DialogClose>
            <Button variant="destructive" onClick={finish}>끝내기</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirm === "restart"} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>처음부터 다시 할까요?</DialogTitle>
            <DialogDescription>
              지금 실행을 끝내고 같은 실습을 새로 시작합니다. 주소 대역이 새로 정해지고, 노드의 설정은 모두 지워집니다.
              {run.status !== "passed" && " 지금 실행은 포기로 기록됩니다."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild><Button variant="outline">취소</Button></DialogClose>
            <Button onClick={restart}>다시 시작</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const label = STATUS_LABELS[status] ?? status;
  if (status === "passed") {
    return <Badge className="bg-success/10 text-success"><CheckCircleIcon weight="fill" aria-hidden />{label}</Badge>;
  }
  if (status === "active" || status === "deploying") {
    return <Badge className="bg-primary/10 text-primary"><CircleDashedIcon weight="bold" aria-hidden />{label}</Badge>;
  }
  return <Badge variant="destructive"><XCircleIcon weight="fill" aria-hidden />{label}</Badge>;
}

function Finished({ run }: { run: LabRun }) {
  if (run.status === "deploy_failed") {
    return (
      <Alert variant="destructive">
        <WarningCircleIcon aria-hidden />
        <AlertTitle>실습 환경을 배포하지 못했습니다</AlertTitle>
        <AlertDescription>{run.error}</AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert>
      {run.status === "passed" ? <CheckCircleIcon aria-hidden /> : <StopCircleIcon aria-hidden />}
      <AlertTitle>
        {run.status === "passed" ? "통과한 실습을 끝냈습니다" : run.status === "expired" ? "시간 제한이 지나 끝났습니다" : "실습을 끝냈습니다"}
      </AlertTitle>
      <AlertDescription>
        실습 환경을 지웠습니다. 마지막 설정은 기록에 남았습니다.
        {run.error && ` (${run.error})`}
      </AlertDescription>
    </Alert>
  );
}

// 남은 시간. 0이 되면 한 번 알린다 (서버는 다음 요청 때 정리한다)
function Countdown({ expiresAt, onExpired }: { expiresAt: string; onExpired: () => void }) {
  const [now, setNow] = useState(Date.now());
  const fired = useRef(false);
  const left = new Date(expiresAt).getTime() - now;
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (left <= 0 && !fired.current) {
      fired.current = true;
      onExpired();
    }
  }, [left, onExpired]);
  const total = Math.max(0, Math.floor(left / 1000));
  const text = `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  return (
    <p className={cn("flex items-center gap-1.5 text-sm", total < 300 ? "text-warning" : "text-muted-foreground")}>
      <ClockCountdownIcon className="size-4" aria-hidden />
      {left > 0 ? <>남은 시간 <span className="font-mono tabular-nums">{text}</span></> : "시간 제한이 지났습니다. 정리하는 중…"}
    </p>
  );
}

function Connect({ nodes }: { nodes: LabRun["nodes"] }) {
  async function copy(command: string) {
    try {
      await navigator.clipboard.writeText(command);
      toast.success("복사했습니다", { description: command });
    } catch {
      toast.error("복사하지 못했습니다. 명령을 직접 선택해 복사하세요.");
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><TerminalWindowIcon aria-hidden />노드 접속</CardTitle>
        <p className="text-sm text-muted-foreground">
          자기 터미널에서 실행하세요. Linux 노드는 셸(sh), 라우터는 FRRouting 설정 셸(vtysh)이 열립니다.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {nodes.map((n) => (
            <li key={n.name} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="w-full shrink-0 text-sm sm:w-24">
                <span className="font-medium">{n.name}</span>{" "}
                <span className="text-muted-foreground">{KIND_LABELS[n.kind] ?? n.kind}</span>
              </span>
              <code className="min-w-0 flex-1 truncate rounded-md bg-muted px-2.5 py-1.5 font-mono text-[0.8rem]">{n.connect}</code>
              <Button variant="ghost" size="icon" onClick={() => copy(n.connect)} aria-label={`${n.name} 접속 명령 복사`}>
                <CopyIcon aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

type ChecksProps = {
  run: LabRun;
  live: boolean;
  verifying: boolean;
  onVerify: () => void;
  onChange: (run: LabRun) => void;
};

// 검사 목록과 마지막 검증 결과. 어려움은 끝날 때까지 통과 개수만 보여 준다
function Checks({ run, live, verifying, onVerify, onChange }: ChecksProps) {
  const [hintBusy, setHintBusy] = useState<string | null>(null);
  const [limits, setLimits] = useState<Record<string, number>>({}); // 검사마다 볼 수 있는 단계 수 (힌트를 열어 봐야 안다)
  const last = run.last_attempt;
  const hidden = run.level === "hard" && live;
  const rows: (Partial<LabResult> & { check_id: string; description: string })[] =
    last && last.results.length > 0 ? last.results : run.checks.map((c) => ({ check_id: c.id, description: c.description }));

  async function hint(checkId: string) {
    setHintBusy(checkId);
    try {
      const h = await api.labHint(run.run_id, checkId);
      setLimits((l) => ({ ...l, [checkId]: h.limit }));
      onChange({ ...run, hints: { ...run.hints, [checkId]: h.hints }, hints_used: run.hints_used + (h.new ? 1 : 0) });
      if (!h.new) toast.info("이 검사에서 볼 수 있는 힌트를 다 봤습니다");
    } catch (e) {
      toast.error("힌트를 열지 못했습니다", { description: errorMessage(e) });
    } finally {
      setHintBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2"><ListChecksIcon aria-hidden />검사</CardTitle>
          {last && (
            <p className={cn("mt-1 text-sm font-medium", last.passed ? "text-success" : "text-foreground")}>
              {last.passed
                ? "모든 검사를 통과했습니다"
                : `${last.total_count}개 중 ${last.passed_count}개 통과`}
              <span className="font-normal text-muted-foreground"> · {formatKst(last.attempted_at)} 검증</span>
            </p>
          )}
        </div>
        {live && (
          <Button onClick={onVerify} disabled={verifying}>
            {verifying ? <SpinnerIcon className="animate-spin" aria-hidden /> : <CheckCircleIcon aria-hidden />}
            {verifying ? "검증 중…" : "검증"}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {hidden ? (
          <p className="text-sm text-muted-foreground">
            어려움에서는 검사 목록과 검사별 결과를 끝낼 때 보여 줍니다. 힌트도 없습니다.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">검사가 없습니다.</p>
        ) : (
          <ol className="divide-y">
            {rows.map((r, i) => {
              const seen = run.hints[r.check_id] ?? [];
              const limit = Math.min(run.hint_limit, limits[r.check_id] ?? run.hint_limit);
              return (
                <li key={r.check_id} className="space-y-2 py-3 first:pt-0 last:pb-0">
                  <div className="flex items-start gap-3">
                    <ResultMark passed={r.passed} />
                    <p className="flex-1 pt-0.5 leading-relaxed">
                      <span className="mr-1.5 font-mono text-sm text-muted-foreground">{i + 1}.</span>
                      {r.description}
                    </p>
                    {live && run.hint_limit > 0 && (
                      <Button variant="ghost" size="sm" onClick={() => hint(r.check_id)}
                        disabled={hintBusy !== null || seen.length >= limit}>
                        {hintBusy === r.check_id ? <SpinnerIcon className="animate-spin" aria-hidden /> : <LightbulbIcon aria-hidden />}
                        힌트 {seen.length}/{limit}
                      </Button>
                    )}
                  </div>
                  {r.message && <p className="text-sm sm:pl-[4.75rem] text-muted-foreground">{r.message}</p>}
                  {r.passed === false && r.output && (
                    <pre className="max-h-64 sm:ml-[4.75rem] overflow-auto rounded-md bg-muted px-3 py-2 font-mono text-[0.8rem] leading-relaxed whitespace-pre-wrap">
                      {r.output}
                    </pre>
                  )}
                  {seen.length > 0 && (
                    <ol className="space-y-1.5 sm:ml-[4.75rem] rounded-md border border-primary/20 bg-accent/40 px-3 py-2 text-sm">
                      {seen.map((h, j) => (
                        <li key={j} className="flex gap-2 leading-relaxed">
                          <LightbulbIcon weight="fill" className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                          <span><span className="font-medium">힌트 {j + 1}</span> <Inline text={h} /></span>
                        </li>
                      ))}
                    </ol>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

// 통과·실패·검증 전을 아이콘과 글자로 같이 보여 준다
function ResultMark({ passed }: { passed?: boolean }) {
  if (passed === undefined) {
    return (
      <span className="flex w-16 shrink-0 items-center gap-1 pt-1 text-xs text-muted-foreground">
        <CircleDashedIcon className="size-4" aria-hidden />검증 전
      </span>
    );
  }
  return (
    <span className={cn("flex w-16 shrink-0 items-center gap-1 pt-1 text-xs font-medium", passed ? "text-success" : "text-destructive")}>
      {passed ? <CheckCircleIcon weight="fill" className="size-4" aria-hidden /> : <XCircleIcon weight="fill" className="size-4" aria-hidden />}
      {passed ? "통과" : "실패"}
    </span>
  );
}

// `명령`을 고정폭 글꼴로 보여 준다
function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) =>
        i % 2 === 1 ? <code key={i} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{part}</code> : part,
      )}
    </>
  );
}

function elapsed(from: string, to: string) {
  const minutes = Math.max(1, Math.round((new Date(to).getTime() - new Date(from).getTime()) / 60000));
  return minutes >= 60 ? `${Math.floor(minutes / 60)}시간 ${minutes % 60}분` : `${minutes}분`;
}
