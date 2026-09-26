import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Activity,
  Ban,
  CheckCircle2,
  CircleHelp,
  Download,
  FileSpreadsheet,
  Loader2,
  Search,
  Trash2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/common/States";
import { useToast } from "@/components/common/Toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton, ToggleGroup, ToggleGroupItem } from "@/components/ui/misc";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, uploadFile } from "@/lib/api";
import { fmtBytes, fmtInt } from "@/lib/format";
import type { HitMeta, HitRuleDetail, HitRuleRow, HitVerdict, JobSnapshot, UploadInfo } from "@/lib/types";
import { cn, download } from "@/lib/utils";

const VERDICT_LABEL: Record<HitVerdict, string> = { GARBAGE: "Garbage (0 hits)", IN_USE: "In use", NO_DATA: "No hit data" };

export function VerdictBadge({ v }: { v: HitVerdict }) {
  if (v === "GARBAGE") return <Badge tone="critical"><Trash2 aria-hidden /> Garbage</Badge>;
  if (v === "IN_USE") return <Badge tone="ok"><CheckCircle2 aria-hidden /> In use</Badge>;
  return <Badge tone="medium"><CircleHelp aria-hidden /> No hit data</Badge>;
}

// ------------------------------------------------------------------ upload
function HitsUpload() {
  const nav = useNavigate();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [pct, setPct] = useState(0);
  const [info, setInfo] = useState<UploadInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [job, setJob] = useState<JobSnapshot | null>(null);

  const pick = (f: File) => {
    setFile(f);
    setInfo(null);
    setErr(null);
    setPct(0);
    uploadFile("hits", f, setPct).then(setInfo).catch((e: Error) => setErr(e.message));
  };

  const start = async () => {
    if (!info) return;
    try {
      const j = await api.startHits(info.id);
      setJob(j);
      const es = new EventSource(api.jobEventsUrl(j.id));
      es.onmessage = (e) => {
        const s: JobSnapshot = JSON.parse(e.data);
        setJob(s);
        if (s.state === "done" && s.session_id) {
          es.close();
          nav(`/hits/${s.session_id}`);
        } else if (s.state === "error" || s.state === "cancelled") es.close();
      };
      es.onerror = () => es.close();
    } catch (e) {
      toast({ title: "Could not start the analysis", description: (e as Error).message, tone: "critical" });
    }
  };

  const running = job && (job.state === "queued" || job.state === "running");
  return (
    <div className="mx-auto max-w-3xl space-y-5 px-6 py-10">
      <div className="flex items-start gap-3">
        <Activity className="mt-1 h-6 w-6 text-primary" />
        <div>
          <h1 className="text-xl font-semibold">Hit count analysis</h1>
          <p className="text-sm text-muted">
            Upload <span className="font-mono">show access-list</span> output with hit counts — Excel (any number of sheets, words in any
            columns), CSV or text. Every rule whose hit counts are all <b>0</b> is marked <b className="text-critical">garbage</b>.
          </p>
        </div>
      </div>
      <section className="card p-6">
        <div
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) pick(f); }}
          className={cn("flex min-h-[190px] flex-col items-center justify-center gap-3 rounded-card border-2 border-dashed p-6 text-center",
            over ? "border-accent bg-accent/5" : "border-border bg-surface-2/40",
            info?.detect.ok && "border-solid border-ok/50 bg-ok/5", (err || info?.detect.ok === false) && "border-solid border-critical/50")}
        >
          {!file ? (
            <button className="flex flex-col items-center gap-2" onClick={() => input.current?.click()}>
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary"><UploadCloud className="h-6 w-6" /></span>
              <span className="font-medium">Drop the hit-count file here or <span className="text-primary">browse</span></span>
              <span className="text-[12.5px] text-muted">.xlsx .xls .xlsb .ods .csv .txt — millions of rows supported</span>
            </button>
          ) : (
            <div className="w-full max-w-md space-y-2 text-left">
              <div className="flex items-center gap-3">
                <FileSpreadsheet className="h-8 w-8 text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-[13px] font-medium">{file.name}</p>
                  <p className="text-[12px] text-muted">{fmtBytes(file.size)}</p>
                </div>
                {!running && (
                  <Button variant="ghost" size="icon-sm" aria-label="Remove file" onClick={() => { setFile(null); setInfo(null); setJob(null); }}>
                    <X />
                  </Button>
                )}
              </div>
              {!info && !err && (
                <div className="h-1 overflow-hidden rounded-full bg-border"><div className="h-full bg-primary" style={{ width: `${pct}%` }} /></div>
              )}
              {info?.detect.ok && (
                <p className="flex items-center gap-2 text-[13px] font-medium text-ok">
                  <CheckCircle2 className="h-4 w-4" /> {info.detect.label}
                  {info.detect.sheets && info.detect.sheets.length > 1 && (
                    <span className="truncate font-normal text-muted">({info.detect.sheets.join(", ")})</span>
                  )}
                </p>
              )}
              {(err || info?.detect.ok === false) && (
                <p className="flex items-center gap-2 text-[13px] text-critical"><XCircle className="h-4 w-4" /> {err ?? info?.detect.error}</p>
              )}
            </div>
          )}
          <input ref={input} type="file" className="hidden" accept=".xlsx,.xlsm,.xlsb,.xls,.ods,.csv,.txt,.log"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = ""; }} />
        </div>

        {job && (
          <div className="mt-5 rounded-input border border-border bg-surface-2/50 p-4">
            {running ? (
              <div className="flex items-center gap-3 text-sm">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                <span className="flex-1">
                  Reading rows… <b className="font-mono">{fmtInt(job.counters.rows ?? 0)}</b> rows ·{" "}
                  <b className="font-mono">{fmtInt(job.counters.rules ?? 0)}</b> rules
                  {job.counters.sheet ? <> · sheet <span className="font-mono">{String(job.counters.sheet)}</span></> : null}
                </span>
                <span className="text-muted">{job.elapsed}s</span>
                <Button size="sm" variant="secondary" onClick={() => api.cancelJob(job.id)}><Ban /> Cancel</Button>
              </div>
            ) : job.state === "error" ? (
              <p className="flex items-center gap-2 text-sm text-critical"><XCircle className="h-4 w-4" /> {job.error}</p>
            ) : job.state === "cancelled" ? (
              <p className="text-sm text-muted">Cancelled.</p>
            ) : null}
          </div>
        )}

        <div className="mt-5 flex justify-end">
          <Button size="lg" disabled={!info?.detect.ok || !!running} onClick={start} className="min-w-40">
            {running ? <Loader2 className="animate-spin" /> : <Activity />} Analyze hit counts
          </Button>
        </div>
      </section>
      <p className="text-[12.5px] text-muted">
        Rules are recognised by their Cisco keywords (<span className="font-mono">RULE:</span>, <span className="font-mono">rule-id</span>,{" "}
        <span className="font-mono">access-list … line N</span>, <span className="font-mono">(hitcnt=N)</span>) wherever they sit in the row;
        every <span className="font-mono">hitcnt</span> on a row counts (extra columns = other devices or snapshots). Table exports with a
        "Rule Name / Hit Count" header are supported too.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- results
const PAGE = 200;

function useHitRows(hid: string, verdict: string, q: string, sort: string) {
  const [total, setTotal] = useState<number | null>(null);
  const [pages, setPages] = useState<Map<number, HitRuleRow[]>>(new Map());
  const loading = useRef<Set<number>>(new Set());
  const gen = useRef(0);

  useEffect(() => {
    gen.current += 1;
    loading.current = new Set();
    setPages(new Map());
    setTotal(null);
    const g = gen.current;
    api.hitsRules(hid, { verdict, q, sort, offset: 0, limit: PAGE }).then((r) => {
      if (g !== gen.current) return;
      setTotal(r.total);
      setPages(new Map([[0, r.rows]]));
    });
  }, [hid, verdict, q, sort]);

  const ensure = useCallback((page: number) => {
    if (pages.has(page) || loading.current.has(page)) return;
    loading.current.add(page);
    const g = gen.current;
    api.hitsRules(hid, { verdict, q, sort, offset: page * PAGE, limit: PAGE }).then((r) => {
      if (g !== gen.current) return;
      setPages((m) => new Map(m).set(page, r.rows));
    });
  }, [hid, verdict, q, sort, pages]);

  const row = (i: number) => pages.get(Math.floor(i / PAGE))?.[i % PAGE];
  return { total, row, ensure };
}

function RuleDrawer({ hid, id, onClose }: { hid: string; id: number | null; onClose: () => void }) {
  const [d, setD] = useState<HitRuleDetail | null>(null);
  useEffect(() => {
    setD(null);
    if (id != null) api.hitsRule(hid, id).then(setD).catch(() => undefined);
  }, [hid, id]);
  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-[min(1000px,70vw)]" aria-describedby={undefined}>
        <div className="flex items-center gap-3 border-b border-border bg-surface px-5 py-3">
          <DialogPrimitive.Title className="flex min-w-0 flex-1 items-center gap-2">
            <span className="truncate font-mono text-[16px] font-semibold">
              {d ? (d.named ? d.name : <span className="font-sans italic text-muted">No name in file — rule-id {d.rule_id}</span>) : "…"}
            </span>
            {d && <VerdictBadge v={d.verdict} />}
          </DialogPrimitive.Title>
          <DialogPrimitive.Close asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Close"><X /></Button>
          </DialogPrimitive.Close>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5 scrollbar-thin">
          {!d ? (
            <Skeleton className="h-40" />
          ) : (
            <>
              <div className={cn("rounded-card border p-4 text-[13.5px]",
                d.verdict === "GARBAGE" ? "border-critical/40 bg-critical/[0.06]" : d.verdict === "IN_USE" ? "border-ok/35 bg-ok/[0.05]" : "border-medium/40 bg-medium/[0.06]")}>
                {d.verdict === "GARBAGE" && <>All <b>{fmtInt(d.hit_values)}</b> hit counts across <b>{fmtInt(d.lines)}</b> line(s) are <b>0</b> — candidate for removal (cross-verify before deleting).</>}
                {d.verdict === "IN_USE" && <>In use: <b>{fmtInt(d.total_hits)}</b> hits across {fmtInt(d.lines)} line(s).
                  {d.zero_elements > 0 && <> {fmtInt(d.zero_elements)} of {fmtInt(d.elements)} element line(s) have 0 hits (partial clean-up possible).</>}</>}
                {d.verdict === "NO_DATA" && <>These lines have no hit count, so Sibit cannot decide.</>}
              </div>
              <dl className="grid grid-cols-4 gap-3 text-[13px]">
                {[["Rule-id", d.rule_id], ["ACL", d.acl ? `${d.acl}${d.acl_line ? ` line ${d.acl_line}` : ""}` : null], ["Action", d.action],
                  ["First seen", `${d.sheet} · row ${d.row}`]].map(([k, v]) => (
                  <div key={k as string} className="rounded-input border border-border bg-surface-2/50 px-3 py-2">
                    <dt className="text-[11px] uppercase tracking-wide text-muted">{k}</dt>
                    <dd className="truncate font-mono">{v ?? "—"}</dd>
                  </div>
                ))}
              </dl>
              <div className="overflow-hidden rounded-card border border-border">
                <table className="w-full text-[12.5px]">
                  <thead className="bg-surface-2 text-left text-[11px] uppercase tracking-wide text-muted">
                    <tr><th className="px-3 py-2">Sheet · row</th><th className="px-3 py-2">Kind</th><th className="px-3 py-2">Hits</th><th className="px-3 py-2">Line</th></tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {d.line_items.map((l, i) => (
                      <tr key={i} className={cn("align-top", l.hit_sum > 0 ? "bg-ok/[0.05]" : l.hit_n > 0 ? "bg-critical/[0.04]" : "")}>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-muted">{l.sheet} · {l.row}</td>
                        <td className="px-3 py-2">{l.kind === "summary" ? <Badge>group</Badge> : l.kind === "table" ? <Badge>table</Badge> : <Badge>element</Badge>}</td>
                        <td className="whitespace-nowrap px-3 py-2 font-mono">
                          {l.hit_n === 0 ? <span className="text-medium">none</span> : (
                            <span className={l.hit_sum > 0 ? "font-semibold text-ok" : "text-critical"}>
                              {l.hits ? l.hits.join(" + ") : fmtInt(l.hit_sum)}
                            </span>
                          )}
                        </td>
                        <td className="break-all px-3 py-2 font-mono">{l.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {d.truncated && <p className="text-[12px] text-muted">Showing the first 5,000 lines of this rule.</p>}
            </>
          )}
        </div>
      </SheetContent>
    </Dialog>
  );
}

function HitsResults({ hid }: { hid: string }) {
  const [params, setParams] = useSearchParams();
  const verdict = params.get("verdict") ?? "GARBAGE";
  const sort = params.get("sort") ?? "";
  const [qInput, setQInput] = useState(params.get("q") ?? "");
  const q = params.get("q") ?? "";
  const [meta, setMeta] = useState<HitMeta | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };
  useEffect(() => {
    api.hitsMeta(hid).then(setMeta).catch((e: Error) => setErr(e.message));
  }, [hid]);
  useEffect(() => {
    const t = setTimeout(() => qInput !== q && set("q", qInput), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  // Large reports take a while to build; fetch with a visible busy state instead of a silent link.
  const exportExcel = async () => {
    setExporting(true);
    try {
      const res = await fetch(api.hitsExportUrl(hid, "xlsx"));
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
      const name = /filename="?([^";]+)"?/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "hit-analysis.xlsx";
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      toast({ title: "Excel report failed", description: (e as Error).message, tone: "critical" });
    } finally {
      setExporting(false);
    }
  };
  const vparam = verdict === "ALL" ? "" : verdict;
  const { total, row, ensure } = useHitRows(hid, vparam, q, sort);
  const parent = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({ count: total ?? 0, getScrollElement: () => parent.current, estimateSize: () => 38, overscan: 20 });
  const items = virt.getVirtualItems();
  useEffect(() => {
    const pagesNeeded = new Set(items.map((it) => Math.floor(it.index / PAGE)));
    pagesNeeded.forEach(ensure);
  }, [items, ensure]);

  const kpis = useMemo(() => meta ? [
    { v: "ALL", label: "Rules", n: meta.rules, tone: "text-text", icon: Activity },
    { v: "GARBAGE", label: "Garbage (0 hits)", n: meta.counts.GARBAGE, tone: "text-critical", icon: Trash2 },
    { v: "IN_USE", label: "In use", n: meta.counts.IN_USE, tone: "text-ok", icon: CheckCircle2 },
    { v: "NO_DATA", label: "No hit data", n: meta.counts.NO_DATA, tone: "text-medium", icon: CircleHelp },
  ] : [], [meta]);

  if (err) return <div className="p-8"><ErrorState message={err} /></div>;
  if (!meta) return <PageSkeleton />;
  return (
    <div className="flex h-full flex-col">
      <div className="space-y-4 border-b border-border p-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <h1 className="flex items-center gap-2 text-lg font-semibold"><Activity className="h-5 w-5 text-primary" /> Hit count analysis</h1>
          <span className="font-mono text-[12.5px] text-muted">{meta.file_name}</span>
          <span className="text-[12.5px] text-muted">
            {fmtInt(meta.rows_read)} rows · {meta.sheets.length} sheet(s) · {fmtInt(meta.lines)} rule lines · {meta.seconds}s
            {meta.warning_count > 0 && <> · {fmtInt(meta.warning_count)} warning(s) in the report</>}
          </span>
          <div className="ml-auto flex gap-2">
            <Button size="sm" onClick={exportExcel} disabled={exporting}>
              {exporting ? <Loader2 className="animate-spin" /> : <Download />} {exporting ? "Preparing Excel report…" : "Excel report"}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => download(api.hitsExportUrl(hid, "csv", vparam, q))}>
              <Download /> CSV of this view
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-3">
          {kpis.map((k) => (
            <button key={k.v} onClick={() => set("verdict", k.v)}
              className={cn("card flex items-center gap-3 p-3 text-left transition-colors hover:border-primary/40",
                verdict === k.v && "border-primary/60 ring-1 ring-primary/30",
                k.v === "GARBAGE" && k.n > 0 && "border-critical/50 bg-critical/[0.05]")}>
              <k.icon className={cn("h-5 w-5", k.tone)} />
              <div>
                <div className="text-[12px] text-muted">{k.label}</div>
                <div className={cn("font-mono text-2xl font-semibold tabular-nums", k.tone)}>{fmtInt(k.n)}</div>
              </div>
            </button>
          ))}
        </div>
        <p className="text-[12.5px] text-muted">
          <b className="text-critical">Garbage</b> = every hit count on every line of the rule, in every column, is 0.
          {meta.partial > 0 && <> {fmtInt(meta.partial)} rule(s) in use have some zero-hit element lines (see each rule).</>}
          {" "}Cross-verify before removing anything.
        </p>
        {meta.unnamed > 0 && (
          <div className="flex items-start gap-2 rounded-input border border-medium/40 bg-medium/[0.07] px-3 py-2 text-[12.5px]">
            <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-medium" />
            <span>
              <b>{fmtInt(meta.unnamed)}</b> rule(s) have no name in this file and are shown by rule-id. Sibit reads names from{" "}
              <span className="font-mono">RULE: name</span> rows, <span className="font-mono">remark rule-id N: L7 RULE: name</span> lines
              (full <span className="font-mono">show access-list</span> output), or a sheet with <span className="font-mono">Rule ID</span>{" "}
              and <span className="font-mono">Rule Name</span> columns — add one of these and upload again.
            </span>
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2.5">
        <div className="relative w-80">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search rule name, rule-id, ACL, sheet…"
            className="pl-8 font-mono text-[13px]" aria-label="Search rules" />
        </div>
        <ToggleGroup type="single" value={verdict} onValueChange={(v) => v && set("verdict", v)} aria-label="Verdict">
          <ToggleGroupItem value="ALL">All</ToggleGroupItem>
          <ToggleGroupItem value="GARBAGE">Garbage</ToggleGroupItem>
          <ToggleGroupItem value="IN_USE">In use</ToggleGroupItem>
          <ToggleGroupItem value="NO_DATA">No data</ToggleGroupItem>
        </ToggleGroup>
        <Select value={sort || "order"} onValueChange={(v) => set("sort", v === "order" ? "" : v)}>
          <SelectTrigger className="h-8 w-48" aria-label="Sort"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="order">File order</SelectItem>
            <SelectItem value="hits">Most hits first</SelectItem>
            <SelectItem value="hits_asc">Fewest hits first</SelectItem>
            <SelectItem value="name">Name</SelectItem>
            <SelectItem value="lines">Most lines first</SelectItem>
          </SelectContent>
        </Select>
        <span className="ml-auto text-[12.5px] tabular-nums text-muted">
          {total == null ? "…" : `${fmtInt(total)} ${verdict === "ALL" ? "" : VERDICT_LABEL[verdict as HitVerdict].toLowerCase() + " "}rules`}
        </span>
      </div>
      {total === 0 ? (
        <EmptyState title="No rules in this view" tone={verdict === "GARBAGE" ? "ok" : "muted"}>
          {verdict === "GARBAGE" ? "No rule has all-zero hit counts." : "Try another filter."}
        </EmptyState>
      ) : (
        <div ref={parent} className="min-h-0 flex-1 overflow-auto scrollbar-thin">
          <div className="sticky top-0 z-10 grid grid-cols-[150px_minmax(260px,2fr)_130px_minmax(140px,1fr)_110px_90px_120px] border-b border-border bg-surface-2/95 text-[11.5px] font-semibold uppercase tracking-wide text-muted backdrop-blur">
            {["Verdict", "Rule", "Rule-id", "Sheet · row", "Total hits", "Lines", "Zero-hit elements"].map((h) => (
              <div key={h} className="px-3 py-2">{h}</div>
            ))}
          </div>
          <div style={{ height: virt.getTotalSize(), position: "relative" }}>
            {items.map((it) => {
              const r = row(it.index);
              return (
                <div key={it.key} onClick={() => r && setOpen(r.id)}
                  className={cn("absolute left-0 grid w-full cursor-pointer grid-cols-[150px_minmax(260px,2fr)_130px_minmax(140px,1fr)_110px_90px_120px] items-center border-b border-border/70 text-[13px] hover:bg-surface-2/70",
                    r?.verdict === "GARBAGE" && "shadow-[inset_3px_0_0_rgb(var(--critical))]")}
                  style={{ height: 38, transform: `translateY(${it.start}px)` }}>
                  {!r ? (
                    <div className="col-span-7 px-3"><Skeleton className="h-4 w-2/3" /></div>
                  ) : (
                    <>
                      <div className="px-3"><VerdictBadge v={r.verdict} /></div>
                      <div className="truncate px-3 font-mono font-medium">
                        {r.named ? r.name : <span className="font-sans font-normal italic text-muted">no name in file</span>}
                      </div>
                      <div className="truncate px-3 font-mono text-muted">{r.rule_id ?? (r.acl ? `${r.acl}:${r.acl_line}` : "—")}</div>
                      <div className="truncate px-3 font-mono text-[12px] text-muted">{r.sheet} · {r.row}</div>
                      <div className={cn("px-3 font-mono tabular-nums", r.total_hits > 0 ? "text-ok" : "text-critical")}>
                        {r.hit_values ? fmtInt(r.total_hits) : "—"}
                      </div>
                      <div className="px-3 font-mono tabular-nums text-muted">{fmtInt(r.lines)}</div>
                      <div className="px-3 font-mono tabular-nums text-muted">{r.elements ? `${fmtInt(r.zero_elements)} / ${fmtInt(r.elements)}` : "—"}</div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      <RuleDrawer hid={hid} id={open} onClose={() => setOpen(null)} />
    </div>
  );
}

export default function HitsPage() {
  const { hid } = useParams();
  return hid ? <HitsResults hid={hid} /> : <HitsUpload />;
}
