import { ArrowDown, ArrowUp, Ban, ListOrdered } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState, ErrorState } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { OrderChange } from "@/lib/types";
import { cn } from "@/lib/utils";

function Stack({
  side,
  first,
  second,
  sid,
}: {
  side: "ASA" | "FTD";
  first: { key: string; id: number; deny: boolean; n: number };
  second: { key: string; id: number; deny: boolean; n: number };
  sid: string;
}) {
  const item = (x: typeof first, i: number) => (
    <Link
      to={`/s/${sid}/rules?rule=${x.id}`}
      className={cn(
        "flex items-center gap-2 rounded-input border px-3 py-2 text-[13px] hover:border-primary/50",
        x.deny ? "border-critical/40 bg-critical/[0.06]" : "border-border bg-surface",
      )}
    >
      <span className="w-5 text-center font-mono text-[11px] text-muted">{i + 1}</span>
      {x.deny && <Ban className="h-3.5 w-3.5 text-critical" aria-label="deny rule" />}
      <span className="flex-1 truncate font-mono font-medium">{x.key}</span>
      <span className="font-mono text-[11.5px] text-muted">{side === "ASA" ? `line ${x.n}` : `pos ${x.n}`}</span>
    </Link>
  );
  return (
    <div className="space-y-1.5">
      <p className="text-[11.5px] font-semibold uppercase tracking-wide text-muted">{side === "ASA" ? "ASA (before)" : "FTD (after)"}</p>
      {item(first, 0)}
      {item(second, 1)}
    </div>
  );
}

export default function OrderPage() {
  const { sid, meta } = useSession();
  const [data, setData] = useState<OrderChange[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.order(sid).then(setData).catch((e: Error) => setErr(e.message));
  }, [sid]);
  const byAcl = useMemo(() => {
    const m = new Map<string, OrderChange[]>();
    for (const o of data ?? []) m.set(o.acl, [...(m.get(o.acl) ?? []), o]);
    return [...m.entries()];
  }, [data]);

  if (err) return <div className="p-8"><ErrorState message={err} /></div>;
  return (
    <div className="space-y-5 p-6">
      <div className="flex items-start gap-3">
        <ListOrdered className="mt-0.5 h-5 w-5 text-primary" />
        <div>
          <h1 className="text-lg font-semibold">Order check</h1>
          <p className="max-w-3xl text-sm text-muted">
            Rules whose position changed relative to a <b>deny</b> rule in the same ACL. On a first-match firewall, a permit that moves
            above a deny (or a deny that moves below a permit) can silently change which traffic is allowed.
          </p>
        </div>
        {data && <Badge tone={data.length ? "high" : "ok"} className="ml-auto">{fmtInt(data.length)} change(s)</Badge>}
      </div>
      {!data ? (
        <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
      ) : data.length === 0 ? (
        <EmptyState title="Relative order preserved" tone="ok">
          Every matched rule keeps the same position relative to the deny rules in its ACL{meta ? ` (${fmtInt(meta.per_acl.length)} ACLs checked)` : ""}.
        </EmptyState>
      ) : (
        byAcl.map(([acl, items]) => (
          <section key={acl} className="card">
            <h2 className="flex items-center gap-2 border-b border-border px-5 py-3 font-semibold">
              <span className="font-mono">{acl}</span>
              <span className="text-[12.5px] font-normal text-muted">{fmtInt(items.length)} change(s)</span>
            </h2>
            <ul className="divide-y divide-border">
              {items.slice(0, 500).map((o, i) => {
                const rule = { key: o.rule_key, id: o.rule_id, deny: false };
                const deny = { key: o.deny_key, id: o.deny_id, deny: true };
                const asaFirst = o.asa_relation === "above";
                const ftdFirst = o.ftd_relation === "above";
                return (
                  <li key={i} className="grid grid-cols-[1fr_auto_1fr] items-center gap-5 px-5 py-4">
                    <Stack side="ASA" sid={sid}
                      first={asaFirst ? { ...rule, n: o.asa_rule_line } : { ...deny, n: o.asa_deny_line }}
                      second={asaFirst ? { ...deny, n: o.asa_deny_line } : { ...rule, n: o.asa_rule_line }} />
                    <div className="flex flex-col items-center gap-1 text-[12px] text-muted">
                      {ftdFirst ? <ArrowUp className="h-5 w-5 text-high" /> : <ArrowDown className="h-5 w-5 text-high" />}
                      <span className="whitespace-nowrap">
                        <span className="font-mono">{o.rule_key}</span> moved {o.ftd_relation}
                      </span>
                      <span>the deny</span>
                    </div>
                    <Stack side="FTD" sid={sid}
                      first={ftdFirst ? { ...rule, n: o.ftd_rule_position } : { ...deny, n: o.ftd_deny_position }}
                      second={ftdFirst ? { ...deny, n: o.ftd_deny_position } : { ...rule, n: o.ftd_rule_position }} />
                  </li>
                );
              })}
            </ul>
            {items.length > 500 && <p className="border-t border-border px-5 py-2 text-[12px] text-muted">Showing 500 of {fmtInt(items.length)} — export to Excel for the full list.</p>}
          </section>
        ))
      )}
    </div>
  );
}
