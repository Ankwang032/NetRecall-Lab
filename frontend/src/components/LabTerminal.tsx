import { useEffect, useRef, useState } from "react";
import { ArrowsClockwiseIcon } from "@phosphor-icons/react";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { api, errorMessage } from "@/api";
import { Button } from "@/components/ui/button";

// 노드 터미널 하나 (웹 터미널, backend/api/lab_terminal.py). 실습 화면에서만 쓰므로 따로 불러온다(lazy)
// 1회용 발급표를 받아 WebSocket을 연다. 서버는 바이너리(출력)와 닫는 이유(텍스트 JSON)를 보낸다
type Props = { runId: number; node: string; shell: string; active: boolean };

export default function LabTerminal({ runId, node, shell, active }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const term = useRef<{ terminal: Terminal; fit: FitAddon } | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [message, setMessage] = useState<string | null>(null);
  const [round, setRound] = useState(0); // 다시 연결할 때 바뀐다

  function send(message: object) {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(message));
  }

  // 터미널 화면은 한 번 만든다. 크기가 바뀌면 서버에도 알린다
  useEffect(() => {
    const terminal = new Terminal({
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      fontSize: 13,
      cursorBlink: true,
      scrollback: 2000,
      theme: themeFromTokens(),
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(box.current!);
    term.current = { terminal, fit };
    const input = terminal.onData((data) => send({ type: "input", data }));
    const resized = terminal.onResize(({ cols, rows }) => send({ type: "resize", cols, rows }));
    const observer = new ResizeObserver(() => box.current?.offsetParent && fit.fit()); // 숨긴 탭은 건너뛴다
    observer.observe(box.current!);
    return () => {
      input.dispose();
      resized.dispose();
      observer.disconnect();
      terminal.dispose();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let opened = false;
    let ws: WebSocket | null = null;
    setStatus("connecting");
    setMessage(null);
    (async () => {
      try {
        const { ticket } = await api.terminalTicket(runId, node, shell);
        if (cancelled) return;
        const scheme = location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${scheme}://${location.host}/lab-runs/${runId}/terminal?ticket=${encodeURIComponent(ticket)}`);
        ws.binaryType = "arraybuffer";
        socket.current = ws;
        ws.onopen = () => {
          opened = true;
          setStatus("open");
          const t = term.current!;
          if (box.current?.offsetParent) t.fit.fit();
          send({ type: "resize", cols: t.terminal.cols, rows: t.terminal.rows });
          t.terminal.focus();
        };
        ws.onmessage = (e) => {
          if (typeof e.data === "string") {
            const m = JSON.parse(e.data);
            if (m.type === "closed") setMessage(m.message);
          } else {
            term.current?.terminal.write(new Uint8Array(e.data));
          }
        };
        ws.onclose = () => {
          if (cancelled) return;
          setStatus("closed");
          setMessage((m) => m ?? (opened ? "연결이 끊겼습니다" : "서버가 접속을 거절했습니다"));
        };
      } catch (e) {
        if (!cancelled) {
          setStatus("closed");
          setMessage(errorMessage(e));
        }
      }
    })();
    return () => {
      cancelled = true;
      ws?.close();
    };
  }, [runId, node, shell, round]);

  useEffect(() => {
    if (!active || !term.current) return;
    if (box.current?.offsetParent) term.current.fit.fit();
    term.current.terminal.focus();
  }, [active]);

  return (
    <div className="space-y-2">
      <div className="flex min-h-7 items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
        {status === "connecting" && "연결하는 중…"}
        {status === "open" && `${node}에 연결됨 (${shell})`}
        {status === "closed" && (
          <>
            <span>{message}</span>
            <Button variant="outline" size="sm" onClick={() => setRound((r) => r + 1)}>
              <ArrowsClockwiseIcon aria-hidden /> 다시 연결
            </Button>
          </>
        )}
      </div>
      <div ref={box} className="h-[22rem] overflow-hidden rounded-md border bg-card p-2" aria-label={`${node} 터미널`} />
    </div>
  );
}

// 색은 테마 토큰에서 읽는다 (라이트·다크 모두)
function themeFromTokens() {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string) => css.getPropertyValue(name).trim() || undefined;
  return {
    background: token("--card"),
    foreground: token("--foreground"),
    cursor: token("--primary"),
    cursorAccent: token("--card"),
    selectionBackground: token("--accent"),
  };
}
