import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { STATUS_LABEL, STATUS_ORDER, fmtInt } from "@/lib/format";
import type { AclCount, Status } from "@/lib/types";

export const STATUS_COLOR: Record<Status, string> = {
  MATCH: "rgb(var(--ok))",
  MATCH_MERGED: "rgb(var(--accent))",
  CHANGED: "rgb(var(--medium))",
  MISSING_IN_FTD: "rgb(var(--critical))",
  EXTRA_IN_FTD: "rgb(var(--primary))",
  UNRESOLVED: "rgb(var(--muted))",
};

const tooltipStyle = {
  background: "rgb(var(--surface))",
  border: "1px solid rgb(var(--border))",
  borderRadius: 8,
  color: "rgb(var(--text))",
  fontSize: 12,
};

export function StatusDonut({ counts, onSelect }: { counts: Record<Status, number>; onSelect?: (s: Status) => void }) {
  const data = STATUS_ORDER.map((s) => ({ status: s, name: STATUS_LABEL[s], value: counts[s] ?? 0 })).filter((d) => d.value > 0);
  const total = data.reduce((a, d) => a + d.value, 0);
  return (
    <div className="flex h-full items-center gap-6">
      <div className="relative h-56 w-56 shrink-0">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius="64%" outerRadius="96%" paddingAngle={data.length > 1 ? 1.5 : 0}
              stroke="none" isAnimationActive={false} onClick={(d) => onSelect?.((d as unknown as { status: Status }).status)} className="cursor-pointer">
              {data.map((d) => (
                <Cell key={d.status} fill={STATUS_COLOR[d.status]} />
              ))}
            </Pie>
            <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: "rgb(var(--text))" }} formatter={(v) => fmtInt(Number(v))} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-2xl font-semibold tabular-nums">{fmtInt(total)}</span>
          <span className="text-[12px] text-muted">rules</span>
        </div>
      </div>
      <ul className="flex-1 space-y-1.5">
        {STATUS_ORDER.map((s) => (
          <li key={s}>
            <button className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-[13px] hover:bg-surface-2" onClick={() => onSelect?.(s)}>
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: STATUS_COLOR[s] }} aria-hidden />
              <span className="flex-1">{STATUS_LABEL[s]}</span>
              <span className="font-mono tabular-nums text-muted">{fmtInt(counts[s] ?? 0)}</span>
              <span className="w-12 text-right font-mono text-[12px] tabular-nums text-muted">
                {total ? `${((100 * (counts[s] ?? 0)) / total).toFixed(1)}%` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AclStackedBar({ perAcl, onSelect }: { perAcl: AclCount[]; onSelect?: (acl: string) => void }) {
  const data = perAcl.slice(0, 14).map((a) => ({ ...a }));
  const h = Math.max(220, data.length * 34 + 60);
  return (
    <div style={{ height: h }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }} barSize={16}>
          <CartesianGrid horizontal={false} stroke="rgb(var(--border))" />
          <XAxis type="number" tick={{ fill: "rgb(var(--muted))", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="acl" width={130} tick={{ fill: "rgb(var(--text))", fontSize: 12, fontFamily: "JetBrains Mono" }}
            axisLine={false} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgb(var(--surface-2))" }} />
          <Legend iconType="square" iconSize={9} wrapperStyle={{ fontSize: 12, color: "rgb(var(--muted))" }} />
          {STATUS_ORDER.map((s, i) => (
            <Bar key={s} dataKey={s} name={STATUS_LABEL[s]} stackId="a" fill={STATUS_COLOR[s]} isAnimationActive={false}
              radius={i === STATUS_ORDER.length - 1 ? [0, 3, 3, 0] : 0} className="cursor-pointer"
              onClick={(d) => onSelect?.((d as unknown as { acl: string }).acl)} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
