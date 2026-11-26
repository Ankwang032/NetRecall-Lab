import type { LabRun } from "@/api";

// 읽기 전용 토폴로지 그림. 노드를 받은 순서대로 한 줄에 놓고, 이웃한 노드의 링크는 직선,
// 떨어진 노드의 링크는 노드 위로 지나는 곡선으로 그린다. 배포할 때 넣은 주소는 노드 아래에 쓴다
const NODE_W = 84;
const NODE_H = 44;
const GAP = 210; // 노드 중심 사이. 주소 한 줄(/30까지 17자)이 이웃 노드 주소와 겹치지 않는 폭
const PAD = 16;
const PAD_X = 48; // 양끝 노드 아래 주소 한 줄(약 140px)이 잘리지 않는 여백
const ARC_SPACE = 40;
const LINE = 15;
const KIND_LABELS: Record<string, string> = { host: "Linux", router: "FRRouting" };

type Props = Pick<LabRun, "nodes" | "links" | "addresses">;

export function LabTopology({ nodes, links, addresses }: Props) {
  const index = new Map(nodes.map((n, i) => [n.name, i]));
  const ends = links.map(({ a, b }) => [a, b].map(split).sort((x, y) => index.get(x.node)! - index.get(y.node)!));
  const arcs = ends.some(([l, r]) => index.get(r.node)! - index.get(l.node)! > 1);
  const top = PAD + (arcs ? ARC_SPACE : 0);
  const cy = top + NODE_H / 2;
  const cx = (node: string) => PAD_X + NODE_W / 2 + index.get(node)! * GAP;

  const byNode = new Map<string, { iface: string; address: string }[]>();
  for (const { interface: endpoint, address } of addresses) {
    const { node, iface } = split(endpoint);
    byNode.set(node, [...(byNode.get(node) ?? []), { iface, address }].sort((x, y) => x.iface.localeCompare(y.iface)));
  }
  const lines = Math.max(0, ...[...byNode.values()].map((a) => a.length));
  const width = PAD_X * 2 + NODE_W + (nodes.length - 1) * GAP;
  const height = top + NODE_H + (lines > 0 ? 14 + lines * LINE : 0) + PAD;

  const label = [
    ...links.map(({ a, b }) => `${a} — ${b}`),
    ...addresses.map((a) => `${a.interface} ${a.address}`),
  ].join(", ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      style={{ maxWidth: width, minWidth: width * 0.8 }} // 더 좁으면 줄이지 않고 가로로 스크롤한다
      role="img"
      aria-label={`토폴로지: ${label}`}
      className="font-mono text-[11px]"
    >
      {ends.map(([l, r], i) => {
        const [x1, x2] = [cx(l.node), cx(r.node)];
        if (index.get(r.node)! - index.get(l.node)! === 1) {
          const [s, e] = [x1 + NODE_W / 2, x2 - NODE_W / 2];
          return (
            <g key={i}>
              <line x1={s} y1={cy} x2={e} y2={cy} className="stroke-muted-foreground" strokeWidth={1.5} />
              <text x={s + 6} y={cy - 6} className="fill-muted-foreground">{l.iface}</text>
              <text x={e - 6} y={cy - 6} textAnchor="end" className="fill-muted-foreground">{r.iface}</text>
            </g>
          );
        }
        const [s, e] = [x1 + 12, x2 - 12];
        return (
          <g key={i}>
            <path d={`M ${s} ${top} C ${s} ${PAD}, ${e} ${PAD}, ${e} ${top}`} fill="none"
              className="stroke-muted-foreground" strokeWidth={1.5} />
            <text x={s + 4} y={top - 6} className="fill-muted-foreground">{l.iface}</text>
            <text x={e - 4} y={top - 6} textAnchor="end" className="fill-muted-foreground">{r.iface}</text>
          </g>
        );
      })}

      {nodes.map((n) => {
        const x = cx(n.name);
        return (
          <g key={n.name}>
            <rect x={x - NODE_W / 2} y={top} width={NODE_W} height={NODE_H} rx={8}
              className={n.kind === "router" ? "fill-accent stroke-primary" : "fill-card stroke-border"} strokeWidth={1.5} />
            <text x={x} y={top + 19} textAnchor="middle" className="fill-foreground font-sans text-[13px] font-semibold">
              {n.name}
            </text>
            <text x={x} y={top + 34} textAnchor="middle" className="fill-muted-foreground font-sans text-[10px]">
              {KIND_LABELS[n.kind] ?? n.kind}
            </text>
            {(byNode.get(n.name) ?? []).map((a, i) => (
              <text key={a.iface} x={x} y={top + NODE_H + 14 + (i + 1) * LINE - 4} textAnchor="middle"
                className="fill-foreground">
                <tspan className="fill-muted-foreground">{a.iface} </tspan>{a.address}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

function split(endpoint: string) {
  const [node, iface] = endpoint.split(":");
  return { node, iface };
}
