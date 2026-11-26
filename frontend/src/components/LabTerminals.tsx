import { lazy, Suspense } from "react";
import { TerminalIcon, XIcon } from "@phosphor-icons/react";
import type { LabRun } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const LabTerminal = lazy(() => import("@/components/LabTerminal"));

// 노드 종류 → 열 수 있는 셸. 앞이 기본 (서버 backend/services/lab_terminal.py SHELLS와 같다)
export const SHELLS: Record<string, string[]> = { host: ["sh"], router: ["vtysh", "sh"] };

export type TerminalSession = { node: string; shell: string };
export const sessionKey = (s: TerminalSession) => `${s.node}:${s.shell}`;

type Props = {
  run: LabRun;
  sessions: TerminalSession[];
  active: string | null;
  onOpen: (node: string, shell?: string) => void;
  onSelect: (key: string) => void;
  onClose: (key: string) => void;
};

// 화면 안의 노드 터미널. 연 터미널은 탭을 바꿔도 연결을 유지한다
export function LabTerminals({ run, sessions, active, onOpen, onSelect, onClose }: Props) {
  const label = (s: TerminalSession) => {
    const kind = run.nodes.find((n) => n.name === s.node)?.kind ?? "host";
    return s.shell === SHELLS[kind][0] ? s.node : `${s.node} (${s.shell})`;
  };
  return (
    <Card>
      <CardHeader className="space-y-1.5">
        <CardTitle className="flex items-center gap-2"><TerminalIcon aria-hidden />터미널</CardTitle>
        <p className="text-sm text-muted-foreground">
          노드를 골라 여세요. 토폴로지 그림에서 노드를 눌러도 됩니다. 아래 접속 명령으로 자기 터미널에서 접속해도 같은 노드에 붙습니다.
        </p>
        <div role="group" aria-label="터미널 열기" className="flex flex-wrap gap-1.5 pt-1">
          {run.nodes.flatMap((n) =>
            (SHELLS[n.kind] ?? ["sh"]).map((shell) => (
              <Button key={`${n.name}:${shell}`} variant="outline" size="sm" onClick={() => onOpen(n.name, shell)}>
                {label({ node: n.name, shell })}
              </Button>
            )),
          )}
        </div>
      </CardHeader>
      {sessions.length > 0 && (
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-1 border-b pb-2">
            {sessions.map((s) => {
              const key = sessionKey(s);
              return (
                <div key={key} className={cn("flex items-center rounded-md", key === active ? "bg-accent text-accent-foreground" : "")}>
                  <button type="button" aria-pressed={key === active} onClick={() => onSelect(key)}
                    className="rounded-md px-2.5 py-1 font-mono text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
                    {label(s)}
                  </button>
                  <Button variant="ghost" size="icon-xs" onClick={() => onClose(key)} aria-label={`${label(s)} 터미널 닫기`}>
                    <XIcon aria-hidden />
                  </Button>
                </div>
              );
            })}
          </div>
          <Suspense fallback={<Skeleton className="h-[24rem] rounded-md" />}>
            {sessions.map((s) => (
              <div key={sessionKey(s)} hidden={sessionKey(s) !== active}>
                <LabTerminal runId={run.run_id} node={s.node} shell={s.shell} active={sessionKey(s) === active} />
              </div>
            ))}
          </Suspense>
        </CardContent>
      )}
    </Card>
  );
}
