import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronRight, CircleHelp, Layers, Search, Shapes } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState } from "@/components/common/States";
import { SeverityBadge, StatusBadge } from "@/components/rules/Badges";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, ToggleGroup, ToggleGroupItem } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { ObjectDetail, ObjectSummary, UnresolvedRef } from "@/lib/types";
import { cn } from "@/lib/utils";

const objCache = new Map<string, ObjectDetail>();

function useObject(sid: string, side: string, name: string | null) {
  const [o, setO] = useState<ObjectDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!name) return;
    const k = `${sid}:${side}:${name}`;
    setErr(null);
    const hit = objCache.get(k);
    if (hit) return setO(hit);
    setO(null);
    let alive = true;
    api
      .object(sid, side, name)
      .then((x) => {
        objCache.set(k, x);
        if (alive) setO(x);
      })
      .catch((e: Error) => alive && setErr(e.message));
    return () => {
      alive = false;
    };
  }, [sid, side, name]);
  return { o, err };
}

/** One member line; members that reference other objects expand in place (cycle-safe). */
function MemberNode({ sid, side, text, refName, exists, path }: { sid: string; side: string; text: string; refName: string | null; exists: boolean; path: string[] }) {
  const [open, setOpen] = useState(false);
  const cyclic = refName != null && path.includes(refName);
  const expandable = !!refName && exists && !cyclic;
  const { o } = useObject(sid, side, open && expandable ? refName : null);
  return (
    <li>
      <button
        disabled={!expandable}
        onClick={() => setOpen((x) => !x)}
        className={cn("flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left font-mono text-[12.5px]", expandable && "hover:bg-surface-2")}
      >
        {expandable ? (
          <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 text-muted transition-transform", open && "rotate-90")} />
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        <span className={cn(!refName && "text-text", refName && "text-primary")}>{text}</span>
        {refName && !exists && <Badge tone="critical" className="ml-1 text-[10px]">undefined</Badge>}
        {cyclic && <Badge tone="high" className="ml-1 text-[10px]">cycle</Badge>}
      </button>
      {open && expandable && (
        <ul className="ml-4 border-l border-border pl-2">
          {!o ? (
            <li><Skeleton className="my-1 h-4 w-40" /></li>
          ) : (
            o.members.map((m, i) => (
              <MemberNode key={i} sid={sid} side={side} text={m.text} refName={m.ref} exists={m.exists} path={[...path, refName!]} />
            ))
          )}
        </ul>
      )}
    </li>
  );
}

function ObjectPanel({ sid, side, name }: { sid: string; side: string; name: string }) {
  const { o, err } = useObject(sid, side, name);
  if (err) return <ErrorState message={err} className="m-6" />;
  if (!o)
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-40" />
      </div>
    );
  return (
    <div className="space-y-5 p-6">
      <div>
        <div className="flex items-center gap-2">
          <Badge tone={o.side === "ASA" ? "primary" : "accent"}>{o.side}</Badge>
          <span className="text-[12.5px] text-muted">{o.kind}{o.line != null && (o.side === "ASA" ? ` · line ${o.line}` : ` · page ${o.line}`)}</span>
        </div>
        <h2 className="mt-1 break-all font-mono text-xl font-semibold">{o.name}</h2>
      </div>
      {o.unresolved.length > 0 && (
        <div className="flex items-start gap-2 rounded-input border border-critical/40 bg-critical/5 p-3 text-[13px]">
          <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-critical" />
          <span>Could not fully expand: <span className="font-mono">{o.unresolved.join(", ")}</span></span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-5">
        <section className="card p-4">
          <h3 className="mb-2 flex items-center gap-2 text-[13px] font-semibold"><Layers className="h-4 w-4 text-muted" /> Definition (tree)</h3>
          <ul className="max-h-[420px] overflow-auto scrollbar-thin">
            {o.members.map((m, i) => (
              <MemberNode key={i} sid={sid} side={side} text={m.text} refName={m.ref} exists={m.exists} path={[o.name]} />
            ))}
          </ul>
        </section>
        <section className="card p-4">
          <h3 className="mb-2 text-[13px] font-semibold">Fully expanded <span className="font-normal text-muted">({fmtInt(o.expanded.length)})</span></h3>
          <div className="flex max-h-[420px] flex-wrap content-start gap-1 overflow-auto scrollbar-thin">
            {o.expanded.length === 0 ? <span className="text-sm text-muted">Empty</span> : o.expanded.map((e) => <span key={e} className="chip chip-neutral">{e}</span>)}
          </div>
        </section>
      </div>
      <section className="card">
        <h3 className="border-b border-border px-4 py-2.5 text-[13px] font-semibold">Used by <span className="font-normal text-muted">({fmtInt(o.used_by_rules.length)} rules)</span></h3>
        {o.used_by_rules.length === 0 ? (
          <p className="px-4 py-4 text-sm text-muted">Not referenced by any compared rule.</p>
        ) : (
          <ul className="max-h-80 divide-y divide-border overflow-auto scrollbar-thin">
            {o.used_by_rules.map((r) => (
              <li key={r.id}>
                <Link to={`/s/${sid}/rules?rule=${r.id}`} className="flex items-center gap-3 px-4 py-2 hover:bg-surface-2/60">
                  <span className="flex-1 font-mono text-[13px]">{r.key}</span>
                  <SeverityBadge severity={r.severity} />
                  <StatusBadge status={r.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ObjectList({ items, selected, onSelect }: { items: ObjectSummary[]; selected: string | null; onSelect: (o: ObjectSummary) => void }) {
  const parent = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: items.length, getScrollElement: () => parent.current, estimateSize: () => 52, overscan: 10 });
  return (
    <div ref={parent} className="min-h-0 flex-1 overflow-auto scrollbar-thin">
      <div style={{ height: v.getTotalSize(), position: "relative" }}>
        {v.getVirtualItems().map((vi) => {
          const o = items[vi.index];
          const key = `${o.side}:${o.name}`;
          return (
            <button
              key={key}
              onClick={() => onSelect(o)}
              className={cn("absolute left-0 flex w-full items-center gap-2 border-b border-border/60 px-4 text-left",
                selected === key ? "bg-primary/10 shadow-[inset_3px_0_0_rgb(var(--primary))]" : "hover:bg-surface-2/60")}
              style={{ height: 52, transform: `translateY(${vi.start}px)` }}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-[13px] font-medium">{o.name}</p>
                <p className="truncate text-[11.5px] text-muted">{o.kind} · {fmtInt(o.expanded_count)} item(s) · used by {fmtInt(o.used_count)}</p>
              </div>
              {o.unresolved.length > 0 && <CircleHelp className="h-4 w-4 text-critical" aria-label="unresolved" />}
              <Badge tone={o.side === "ASA" ? "primary" : "accent"} className="text-[10px]">{o.side}</Badge>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function ObjectsPage() {
  const { sid, rows } = useSession();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [side, setSide] = useState(params.get("side") ?? "");
  const [data, setData] = useState<{ total: number; items: ObjectSummary[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const selParam = params.get("obj");
  const sel = selParam ? { side: selParam.slice(0, 3), name: selParam.slice(4) } : null;
  const setSel = (o: { side: string; name: string } | null) => {
    const p = new URLSearchParams(params);
    if (o) p.set("obj", `${o.side}:${o.name}`);
    else p.delete("obj");
    setParams(p, { replace: true });
  };
  useEffect(() => {
    const p = new URLSearchParams(params);
    if (q) p.set("q", q);
    else p.delete("q");
    if (side) p.set("side", side);
    else p.delete("side");
    if (p.toString() !== params.toString()) setParams(p, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, side]);
  const [unres, setUnres] = useState<UnresolvedRef[] | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api.objects(sid, q, side).then((d) => { setData(d); setErr(null); }).catch((e: Error) => setErr(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [sid, q, side]);
  useEffect(() => {
    api.warnings(sid).then((w) => setUnres(w.unresolved)).catch(() => setUnres([]));
  }, [sid]);

  return (
    <Tabs defaultValue="lookup" className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-3">
        <TabsList>
          <TabsTrigger value="lookup"><Shapes /> Lookup</TabsTrigger>
          <TabsTrigger value="unresolved"><CircleHelp /> Unresolved ({unres ? fmtInt(unres.length) : "…"})</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="lookup" className="flex min-h-0 flex-1 data-[state=inactive]:hidden">
        <aside className="flex w-[380px] shrink-0 flex-col border-r border-border bg-surface">
          <div className="space-y-2 border-b border-border p-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Object name or IP (e.g. 192.0.2.10)" className="pl-8 font-mono text-[13px]" aria-label="Search objects" />
            </div>
            <div className="flex items-center justify-between">
              <ToggleGroup type="single" value={side || "all"} onValueChange={(v) => setSide(!v || v === "all" ? "" : v)} aria-label="Side">
                <ToggleGroupItem value="all">All</ToggleGroupItem>
                <ToggleGroupItem value="ASA">ASA</ToggleGroupItem>
                <ToggleGroupItem value="FTD">FTD</ToggleGroupItem>
              </ToggleGroup>
              <span className="text-[12px] text-muted">{data ? `${fmtInt(data.total)} objects` : ""}</span>
            </div>
          </div>
          {err ? (
            <ErrorState message={err} className="m-3" />
          ) : !data ? (
            <div className="space-y-2 p-3">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
          ) : data.items.length === 0 ? (
            <EmptyState title="No objects found">{q ? <>Nothing matches <span className="font-mono">{q}</span>.</> : null}</EmptyState>
          ) : (
            <ObjectList items={data.items} selected={sel ? `${sel.side}:${sel.name}` : null} onSelect={setSel} />
          )}
        </aside>
        <div className="min-w-0 flex-1 overflow-auto scrollbar-thin">
          {sel ? (
            <ObjectPanel key={`${sel.side}:${sel.name}`} sid={sid} side={sel.side} name={sel.name} />
          ) : (
            <EmptyState title="Select an object" className="h-full">
              Look up any object or group from either side to see its fully expanded contents and every rule that uses it.
            </EmptyState>
          )}
        </div>
      </TabsContent>
      <TabsContent value="unresolved" className="min-h-0 flex-1 overflow-auto p-6 scrollbar-thin data-[state=inactive]:hidden">
        {!unres ? (
          <Skeleton className="h-40" />
        ) : unres.length === 0 ? (
          <EmptyState title="Every object was resolved" tone="ok">All object and group references on both sides expanded to real IPs and ports.</EmptyState>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-surface-2 text-left text-[11.5px] uppercase tracking-wide text-muted">
                <tr><th className="px-4 py-2">Side</th><th className="px-4 py-2">Name</th><th className="px-4 py-2">Reason</th><th className="px-4 py-2">Used by</th></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {unres.map((u) => (
                  <tr key={`${u.side}:${u.name}`} className="align-top">
                    <td className="px-4 py-2.5"><Badge tone={u.side === "ASA" ? "primary" : "accent"}>{u.side}</Badge></td>
                    <td className="px-4 py-2.5 font-mono">{u.name}</td>
                    <td className="px-4 py-2.5 text-muted">{u.reason}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {u.used_by.slice(0, 12).map((id) => (
                          <Link key={id} to={`/s/${sid}/rules?rule=${id}`} className="chip chip-neutral hover:border-primary">{rows?.[id]?.key ?? `#${id}`}</Link>
                        ))}
                        {u.used_by.length > 12 && <span className="text-[12px] text-muted">+{u.used_by.length - 12}</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}
