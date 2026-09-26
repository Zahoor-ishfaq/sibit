import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  FileWarning,
  Gauge,
  ListOrdered,
  MinusCircle,
  PencilLine,
  PlusCircle,
  Rows3,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useState, type ComponentType } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AclStackedBar, StatusDonut } from "@/components/charts/Charts";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/common/States";
import { FlagChip, SeverityBadge, StatusBadge } from "@/components/rules/Badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { fmtInt, fmtPct, NUMBERING_LABEL } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { ParseWarning, UnresolvedRef } from "@/lib/types";
import { cn } from "@/lib/utils";

function Kpi({
  label,
  value,
  icon: Icon,
  tone,
  to,
  prominent,
  sub,
}: {
  label: string;
  value: number;
  icon: ComponentType<{ className?: string }>;
  tone: string;
  to: string;
  prominent?: boolean;
  sub?: string;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "card group relative flex flex-col gap-2 overflow-hidden p-4 transition-colors hover:border-primary/40",
        prominent && value > 0 && "border-critical/60 bg-critical/[0.06] ring-1 ring-critical/30",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[12.5px] font-medium text-muted">{label}</span>
        <Icon className={cn("h-4 w-4", tone)} />
      </div>
      <span className={cn("font-mono text-[28px] font-semibold leading-none tabular-nums", prominent && value > 0 && "text-critical")}>
        {fmtInt(value)}
      </span>
      <span className="flex items-center gap-1 text-[12px] text-muted">
        {sub ?? "View rules"} <ArrowRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
      </span>
    </Link>
  );
}

function WarningsDialog({ open, onOpenChange, sid }: { open: boolean; onOpenChange: (o: boolean) => void; sid: string }) {
  const [data, setData] = useState<{ warnings: ParseWarning[]; unresolved: UnresolvedRef[] } | null>(null);
  useEffect(() => {
    if (open && !data) api.warnings(sid).then(setData).catch(() => setData({ warnings: [], unresolved: [] }));
  }, [open, sid, data]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Parse warnings</DialogTitle>
          <DialogDescription>Lines Sibit could not fully interpret. Parsing never stops on unknown syntax; these are listed so nothing is silently skipped.</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="warnings">
          <TabsList>
            <TabsTrigger value="warnings">Warnings ({data?.warnings.length ?? "…"})</TabsTrigger>
            <TabsTrigger value="unresolved">Unresolved objects ({data?.unresolved.length ?? "…"})</TabsTrigger>
          </TabsList>
          <TabsContent value="warnings" className="mt-3 max-h-[60vh] overflow-auto scrollbar-thin">
            {data?.warnings.length === 0 && <EmptyState title="No parse warnings" tone="ok" />}
            <table className="w-full text-[13px]">
              <tbody className="divide-y divide-border">
                {data?.warnings.map((w, i) => (
                  <tr key={i} className="align-top">
                    <td className="w-14 py-2 pr-2"><Badge tone={w.source === "ASA" ? "primary" : "accent"}>{w.source}</Badge></td>
                    <td className="w-20 py-2 pr-2 font-mono text-muted">{w.line != null ? (w.source === "ASA" ? `L${w.line}` : `p.${w.line}`) : "—"}</td>
                    <td className="py-2 pr-2">{w.message}</td>
                    <td className="max-w-[340px] break-all py-2 font-mono text-[12px] text-muted">{w.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TabsContent>
          <TabsContent value="unresolved" className="mt-3 max-h-[60vh] overflow-auto scrollbar-thin">
            {data?.unresolved.length === 0 && <EmptyState title="Every object was resolved" tone="ok" />}
            <table className="w-full text-[13px]">
              <tbody className="divide-y divide-border">
                {data?.unresolved.map((u, i) => (
                  <tr key={i}>
                    <td className="w-14 py-2"><Badge tone={u.side === "ASA" ? "primary" : "accent"}>{u.side}</Badge></td>
                    <td className="py-2 font-mono">{u.name}</td>
                    <td className="py-2 text-muted">{u.reason}</td>
                    <td className="py-2 text-right text-muted">used by {u.used_by.length} rule(s)</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

export default function DashboardPage() {
  const { sid, meta, error, reloadMeta } = useSession();
  const nav = useNavigate();
  const [warnOpen, setWarnOpen] = useState(false);
  if (error) return <div className="p-8"><ErrorState message={error} onRetry={reloadMeta} /></div>;
  if (!meta) return <PageSkeleton />;

  const st = meta.counts.status;
  const cal = meta.calibration;
  const base = `/s/${sid}/rules`;
  const byName = cal.match_rate;

  return (
    <div className="space-y-5 p-6">
      {/* Calibration banner */}
      <div className={cn("card flex items-center gap-4 px-4 py-3", byName >= 95 ? "border-ok/40" : byName >= 70 ? "border-medium/40" : "border-critical/40")}>
        <Gauge className={cn("h-5 w-5 shrink-0", byName >= 95 ? "text-ok" : byName >= 70 ? "text-medium" : "text-critical")} />
        <p className="flex-1 text-sm">
          Matched <b className="font-mono">{fmtPct(byName)}</b> of rules by name (<b>{cal.strategy}</b> numbering
          {cal.requested === "auto" ? ", auto-calibrated per ACL" : `, forced: ${NUMBERING_LABEL[cal.requested]}`}).
          {cal.matched_by_content > 0 && <> {fmtInt(cal.matched_by_content)} more matched by content.</>}
        </p>
        <Button variant="ghost" size="sm" onClick={() => setWarnOpen(true)}>
          <FileWarning /> Parse warnings ({fmtInt(meta.warning_count)}) · unresolved ({fmtInt(meta.unresolved_count)})
        </Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-6 gap-4">
        <Kpi label="Total rules" value={meta.counts.total} icon={Rows3} tone="text-muted" to={base} sub={`${fmtInt(meta.asa_summary.rules)} ASA · ${fmtInt(meta.ftd_summary.rules)} FTD`} />
        <Kpi label="Match" value={st.MATCH + st.MATCH_MERGED} icon={CheckCircle2} tone="text-ok" to={`${base}?status=MATCH,MATCH_MERGED`}
          sub={st.MATCH_MERGED ? `${fmtInt(st.MATCH_MERGED)} merged` : undefined} />
        <Kpi label="Changed" value={st.CHANGED} icon={PencilLine} tone="text-medium" to={`${base}?status=CHANGED`} />
        <Kpi label="Missing in FTD" value={st.MISSING_IN_FTD} icon={MinusCircle} tone="text-critical" to={`${base}?status=MISSING_IN_FTD`} />
        <Kpi label="Extra in FTD" value={st.EXTRA_IN_FTD} icon={PlusCircle} tone="text-primary" to={`${base}?status=EXTRA_IN_FTD`} />
        <Kpi label="Critical risks" value={meta.counts.severity.critical} icon={ShieldAlert} tone="text-critical" to={`${base}?severity=critical`}
          prominent sub={`${fmtInt(meta.counts.severity.high)} high · ${fmtInt(meta.counts.severity.medium)} medium`} />
      </div>

      <div className="grid grid-cols-5 gap-5">
        <section className="card col-span-2 p-5">
          <h2 className="mb-3 font-semibold">Status distribution</h2>
          <StatusDonut counts={st} onSelect={(s) => nav(`${base}?status=${s}`)} />
        </section>
        <section className="card col-span-3 p-5">
          <h2 className="mb-3 font-semibold">Status per ACL</h2>
          <AclStackedBar perAcl={meta.per_acl} onSelect={(acl) => nav(`${base}?acl=${encodeURIComponent(acl)}`)} />
        </section>
      </div>

      <div className="grid grid-cols-5 gap-5">
        <section className="card col-span-3">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h2 className="font-semibold">Top risks</h2>
            <Link to={`${base}?severity=critical,high`} className="text-[13px] text-primary hover:underline">All critical & high</Link>
          </div>
          {meta.top_risks.length === 0 ? (
            <EmptyState title="No critical or high risks" tone="ok">Nothing became wider or lost a deny rule.</EmptyState>
          ) : (
            <ul className="divide-y divide-border">
              {meta.top_risks.map((r) => (
                <li key={r.id}>
                  <Link to={`${base}?rule=${r.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-surface-2/60">
                    <SeverityBadge severity={r.severity} />
                    <span className="w-44 truncate font-mono text-[13px] font-medium">{r.key}</span>
                    <div className="flex min-w-0 flex-1 flex-wrap gap-1">
                      {r.flags.slice(0, 3).map((f) => <FlagChip key={f} code={f} />)}
                    </div>
                    {!r.enabled && <Badge>Disabled</Badge>}
                    <StatusBadge status={r.status} />
                    <ChevronRight className="h-4 w-4 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card col-span-2 p-5">
          <h2 className="mb-3 font-semibold">Comparison details</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-[13px]">
            <dt className="text-muted">ASA hostname</dt><dd className="font-mono">{meta.asa_summary.hostname ?? "—"}</dd>
            <dt className="text-muted">ASA version</dt><dd className="font-mono">{meta.asa_summary.version ?? "—"}</dd>
            <dt className="text-muted">ASA objects / groups</dt>
            <dd className="font-mono">{fmtInt(meta.asa_summary.network_objects + meta.asa_summary.service_objects)} / {fmtInt(meta.asa_summary.network_groups + meta.asa_summary.service_groups + meta.asa_summary.protocol_groups)}</dd>
            <dt className="text-muted">FMC policy</dt><dd className="truncate font-mono" title={meta.ftd_summary.policy}>{meta.ftd_summary.policy ?? "—"}</dd>
            <dt className="text-muted">PDF pages</dt><dd className="font-mono">{fmtInt(meta.ftd_summary.pages)}</dd>
            <dt className="text-muted">Referenced objects</dt><dd className="font-mono">{fmtInt(meta.ftd_summary.referenced_objects)}</dd>
            <dt className="text-muted">Secret lines ignored</dt><dd className="font-mono">{fmtInt(meta.asa_summary.secret_lines_removed)}</dd>
            <dt className="text-muted">Processing time</dt>
            <dd className="font-mono">{(Object.values(meta.seconds) as number[]).reduce((a, b) => a + b, 0).toFixed(1)}s</dd>
          </dl>
          <div className="mt-4 flex gap-2">
            <Button variant="secondary" size="sm" asChild>
              <Link to={`/s/${sid}/order`}><ListOrdered /> Order changes ({fmtInt(meta.order_change_count)})</Link>
            </Button>
            {meta.counts.status.UNRESOLVED > 0 && (
              <Button variant="secondary" size="sm" asChild>
                <Link to={`${base}?status=UNRESOLVED`}><CircleHelp /> Unresolved ({fmtInt(meta.counts.status.UNRESOLVED)})</Link>
              </Button>
            )}
          </div>
        </section>
      </div>
      <WarningsDialog open={warnOpen} onOpenChange={setWarnOpen} sid={sid} />
    </div>
  );
}
