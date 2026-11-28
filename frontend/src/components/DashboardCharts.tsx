import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// 대시보드의 CSS 막대 차트. 색은 테마 토큰(bg-grade-*, bg-stage-* 등)으로만 칠한다 (§E-1).
// 막대는 24px까지, 맞닿은 칸은 2px 틈으로 나눈다. 마우스를 올리거나 키보드로 고르면 값을 보여 주고,
// 같은 값은 "표로 보기"에도 있다 (dataviz 지침)

export type Segment = { label: string; value: number; color: string };

export type Column = {
  key: string;
  segments: Segment[]; // 아래부터 쌓는다
  label: string;       // 접근성 이름 (값 포함)
  tip: ReactNode;
  cap?: string;        // 막대 위에 쓸 값
};

const total = (segments: Segment[]) => segments.reduce((sum, s) => sum + s.value, 0);

// 눈금이 0·절반·끝이 되도록 끝값을 짝수로 올린다
function niceMax(value: number) {
  const step = 10 ** Math.floor(Math.log10(Math.max(value, 1)));
  return [1, 2, 4, 6, 8, 10].map((k) => k * step).find((v) => v >= value && v % 2 === 0) ?? 10 * step;
}

export function ColumnChart({ columns, axis, max, unit = "", height = 144 }: {
  columns: Column[];
  axis: (string | null)[]; // 칸마다 아래에 쓸 글자
  max?: number;            // 없으면 값에 맞춘다
  unit?: string;
  height?: number;
}) {
  const top = max ?? niceMax(Math.max(...columns.map((c) => total(c.segments))));
  return (
    <div className="pl-9">
      <div className="relative" style={{ height }}>
        {[0, top / 2, top].map((tick) => (
          <div key={tick} className="absolute inset-x-0 border-t" style={{ bottom: `${(tick / top) * 100}%` }}>
            <span className="absolute right-full mr-2 -translate-y-1/2 text-xs text-muted-foreground tabular-nums">
              {tick}{unit}
            </span>
          </div>
        ))}
        <div className="absolute inset-0 flex items-end gap-0.5">
          {columns.map((column, i) => (
            <ColumnBar key={column.key} column={column} max={top}
              align={i < columns.length / 4 ? "left" : i >= (columns.length * 3) / 4 ? "right" : "center"} />
          ))}
        </div>
      </div>
      <div className="mt-1.5 flex gap-0.5 text-xs text-muted-foreground" aria-hidden>
        {axis.map((label, i) => (
          <span key={i} className="flex-1 text-center whitespace-nowrap">{label}</span>
        ))}
      </div>
    </div>
  );
}

function ColumnBar({ column, max, align }: { column: Column; max: number; align: TipAlign }) {
  const sum = total(column.segments);
  const visible = column.segments.filter((s) => s.value > 0);
  const height = `${(sum / max) * 100}%`;
  return (
    // 칸 전체가 마우스·키보드 대상이다 (막대보다 넓게)
    <div tabIndex={0} aria-label={column.label}
      className="group relative flex h-full flex-1 flex-col items-center justify-end rounded-sm outline-none hover:bg-muted/50 focus-visible:bg-muted/70 focus-visible:ring-2 focus-visible:ring-ring/50">
      {sum > 0 && (
        <div className="flex w-full max-w-6 flex-col-reverse gap-0.5" style={{ height, minHeight: 2 }}>
          {visible.map((s, i) => (
            <div key={s.label} className={cn(s.color, i === visible.length - 1 && "rounded-t-[4px]")} style={{ flex: `${s.value} 1 0` }} />
          ))}
        </div>
      )}
      {column.cap && sum > 0 && (
        <span className="absolute text-xs text-muted-foreground tabular-nums" style={{ bottom: `calc(${height} + 4px)` }}>
          {column.cap}
        </span>
      )}
      <Tip align={align}>{column.tip}</Tip>
    </div>
  );
}

// 가로 막대 하나에 여러 부분을 쌓는다 (전체 중 몇 장이 어느 단계인지)
export function StackedBar({ segments, label, tip }: { segments: Segment[]; label: string; tip: ReactNode }) {
  return (
    <div tabIndex={0} aria-label={label} className="group relative flex h-6 min-w-0 flex-1 items-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
      <div className="flex h-2 w-full gap-0.5 overflow-hidden rounded-full group-hover:opacity-85">
        {segments.filter((s) => s.value > 0).map((s) => (
          <div key={s.label} className={s.color} style={{ flex: `${s.value} 1 0` }} />
        ))}
      </div>
      <Tip align="center">{tip}</Tip>
    </div>
  );
}

// 0~1 비율 막대. 빈 부분은 트랙으로 보인다
export function Meter({ value, color, label, tip }: { value: number; color: string; label: string; tip: ReactNode }) {
  return (
    <div tabIndex={0} aria-label={label} className="group relative flex h-6 min-w-0 flex-1 items-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full group-hover:opacity-85", color)} style={{ width: `${value * 100}%` }} />
      </div>
      <Tip align="center">{tip}</Tip>
    </div>
  );
}

type TipAlign = "left" | "center" | "right";

function Tip({ children, align }: { children: ReactNode; align: TipAlign }) {
  return (
    <div aria-hidden className={cn(
      "pointer-events-none absolute bottom-full z-10 mb-1.5 hidden rounded-md border bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap text-popover-foreground shadow-md group-hover:block group-focus-visible:block",
      align === "left" ? "left-0" : align === "right" ? "right-0" : "left-1/2 -translate-x-1/2",
    )}>
      {children}
    </div>
  );
}

// 풍선 안: 값이 먼저(굵게), 이름은 뒤. 계열은 짧은 선으로 표시한다
export function TipRows({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="space-y-0.5">
      <p className="text-muted-foreground">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-1.5">
          {r.color && <span className={cn("h-0.5 w-3 rounded-full", r.color)} />}
          <span className="font-semibold tabular-nums">{r.value}</span>
          <span className="text-muted-foreground">{r.label}</span>
        </p>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; value?: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span className={cn("size-2.5 rounded-[3px]", item.color)} aria-hidden />
          {item.label}
          {item.value !== undefined && <span className="text-foreground tabular-nums">{item.value}</span>}
        </li>
      ))}
    </ul>
  );
}

export function TableView({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <details className="text-sm">
      <summary className="w-fit cursor-pointer text-muted-foreground select-none hover:text-foreground">표로 보기</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left tabular-nums">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>{head.map((h) => <th key={h} className="border-b px-2 py-1.5 font-medium whitespace-nowrap text-muted-foreground">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b last:border-0">
                {row.map((cell, j) => <td key={j} className="px-2 py-1.5 whitespace-nowrap">{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
