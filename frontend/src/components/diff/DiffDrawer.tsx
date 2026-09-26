import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Code2,
  Copy,
  Diff,
  GitMerge,
  Info,
  Link2,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { DisabledBadge, FlagChip, SeverityBadge, StatusBadge, ValueChip } from "@/components/rules/Badges";
import { ErrorState } from "@/components/common/States";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger, Skeleton, ToggleGroup, ToggleGroupItem } from "@/components/ui/misc";
import { Tip } from "@/components/ui/tooltip";
import { useToast } from "@/components/common/Toast";
import { api } from "@/lib/api";
import { FIELD_LABEL, fieldChips, findingText } from "@/lib/format";
import { asaTokens, ftdLines } from "@/lib/rawdiff";
import type { Detail, FieldName } from "@/lib/types";
import { cn, copyText } from "@/lib/utils";

const FIELDS: FieldName[] = ["action", "enabled", "src", "dst", "services", "log", "comment"];
const detailCache = new Map<string, Detail>();

function useDetail(sid: string, id: number | null) {
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (id == null) return;
    const k = `${sid}:${id}`;
    const hit = detailCache.get(k);
    setErr(null);
    if (hit) {
      setD(hit);
      return;
    }
    setD(null);
    let alive = true;
    api
      .rule(sid, id)
      .then((x) => {
        detailCache.set(k, x);
        if (alive) setD(x);
      })
      .catch((e: Error) => alive && setErr(e.message));
    return () => {
      alive = false;
    };
  }, [sid, id]);
  return { d, err };
}

function RiskBox({ d }: { d: Detail }) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const tone = d.severity === "critical" ? "critical" : d.severity === "high" ? "high" : d.severity === "medium" ? "medium" : d.status === "MATCH" || d.status === "MATCH_MERGED" ? "ok" : "low";
  const Icon = tone === "ok" ? ShieldCheck : tone === "low" ? Info : ShieldAlert;
  const copy = async () => {
    const ok = await copyText(findingText(d));
    setCopied(ok);
    toast({ title: ok ? "Finding copied" : "Copy failed", description: ok ? "Paste it into your ticket." : undefined, tone: ok ? "ok" : "critical" });
    setTimeout(() => setCopied(false), 1600);
  };
  const border = { critical: "border-critical/40 bg-critical/[0.06]", high: "border-high/40 bg-high/[0.06]", medium: "border-medium/40 bg-medium/[0.06]", ok: "border-ok/35 bg-ok/[0.05]", low: "border-border bg-surface" }[tone];
  const text = { critical: "text-critical", high: "text-high", medium: "text-medium", ok: "text-ok", low: "text-low" }[tone];
  return (
    <div className={cn("rounded-card border p-4", border)}>
      <div className="flex items-start gap-3">
        <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", text)} aria-hidden />
        <p className="flex-1 text-[13.5px] leading-relaxed">{d.explanation}</p>
        <Button size="sm" variant="secondary" onClick={copy} className="shrink-0">
          {copied ? <Check /> : <Copy />} Copy finding
        </Button>
      </div>
      {d.flags.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-border/70 pt-3">
          {d.flags.map((f) => (
            <li key={f.code} className="flex items-start gap-2 text-[12.5px]">
              <FlagChip code={f.code} severity={f.severity} />
              <span className="pt-0.5 text-muted">{f.message}</span>
            </li>
          ))}
        </ul>
      )}
      {d.notes.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-border/70 pt-3">
          {d.notes.map((n) => (
            <li key={n} className="flex items-start gap-2 text-[12.5px] text-muted">
              <GitMerge className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden /> {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FieldTable({ d, expanded }: { d: Detail; expanded: boolean }) {
  return (
    <div className="overflow-hidden rounded-card border border-border">
      <div className="grid grid-cols-[132px_1fr_1fr] border-b border-border bg-surface-2 text-[11.5px] font-semibold uppercase tracking-wide text-muted">
        <div className="px-3 py-2">Field</div>
        <div className="border-l border-border px-3 py-2">ASA (before){d.asa && <span className="ml-2 font-mono normal-case text-muted/80">line {d.asa.line_no}</span>}</div>
        <div className="border-l border-border px-3 py-2">FTD (after){d.ftd?.position != null && <span className="ml-2 font-mono normal-case text-muted/80">#{d.ftd.position}</span>}</div>
      </div>
      {FIELDS.map((f) => {
        const diff = d.diffs[f];
        if (!diff) return null;
        const changed = diff.changed && !diff.ignored && !!d.asa && !!d.ftd;
        const asaChips = fieldChips(diff, "asa", expanded, d);
        const ftdChips = fieldChips(diff, "ftd", expanded, d);
        const many = (n: number) => n > 40;
        return (
          <div key={f} className={cn("grid grid-cols-[132px_1fr_1fr] border-b border-border/70 last:border-b-0",
            changed && "bg-medium/[0.07] shadow-[inset_3px_0_0_rgb(var(--medium))]")}>
            <div className="flex items-start gap-1.5 px-3 py-2.5 text-[13px] font-medium">
              {changed && <Diff className="mt-0.5 h-3.5 w-3.5 shrink-0 text-medium" aria-label="changed" />}
              {FIELD_LABEL[f]}
              {diff.ignored && <Tip content="Comment differences are ignored (see Options)"><Badge className="ml-1 text-[10px]">ignored</Badge></Tip>}
            </div>
            {[asaChips, ftdChips].map((chips, i) => {
              const missing = i === 0 ? !d.asa : !d.ftd;
              return (
                <div key={i} className="flex min-w-0 flex-wrap content-start gap-1 border-l border-border/70 px-3 py-2">
                  {missing ? (
                    <span className="text-[12.5px] italic text-muted">{i === 0 ? "Not in ASA" : "Not in FTD"}</span>
                  ) : chips.length === 0 ? (
                    <span className="text-muted/60">—</span>
                  ) : (
                    <>
                      {(many(chips.length) ? chips.slice(0, 40) : chips).map((c, j) => <ValueChip key={j} chip={c} />)}
                      {many(chips.length) && <span className="self-center text-[12px] text-muted">+{chips.length - 40} more</span>}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function RawView({ d }: { d: Detail }) {
  const [open, setOpen] = useState(false);
  const toks = asaTokens(d);
  const lines = ftdLines(d);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-2 text-[13px] font-medium text-muted hover:text-text">
          <Code2 className="h-4 w-4" /> Raw config
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="min-w-0">
            <p className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-muted">ASA line</p>
            <pre className="mono overflow-x-auto whitespace-pre-wrap break-all rounded-input border border-border bg-surface-2/60 p-3 text-[12px] leading-relaxed">
              {d.asa ? (
                <>
                  {d.asa.comment && <span className="text-muted">{`! remark ${d.asa.comment}\n`}</span>}
                  {toks.map((t, i) =>
                    t.mark === "removed" ? <mark key={i} className="rounded bg-critical/20 px-0.5 text-critical">{t.text}</mark> : <span key={i}>{t.text}</span>,
                  )}
                </>
              ) : (
                <span className="italic text-muted">No ASA origin</span>
              )}
            </pre>
          </div>
          <div className="min-w-0">
            <p className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-muted">FTD rule block</p>
            <pre className="mono max-h-[420px] overflow-auto rounded-input border border-border bg-surface-2/60 py-2 text-[12px] leading-relaxed scrollbar-thin">
              {d.ftd ? (
                lines.map((l, i) => (
                  <div key={i} className={cn("px-3", l.mark === "added" && "bg-ok/15 text-ok")}>
                    <span className="mr-2 inline-block w-2 select-none text-muted/60" aria-hidden>{l.mark === "added" ? "+" : " "}</span>
                    {l.text}
                  </div>
                ))
              ) : (
                <span className="px-3 italic text-muted">Not in FTD</span>
              )}
            </pre>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function DiffDrawer({
  sid,
  id,
  onClose,
  onPrev,
  onNext,
  position,
}: {
  sid: string;
  id: number | null;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  position: string;
}) {
  const { d, err } = useDetail(sid, id);
  const [expanded, setExpanded] = useState(true);
  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        className="w-[min(1080px,72vw)]"
        aria-describedby={undefined}
        // Focus the panel itself, not the first button (which would pop its tooltip).
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          (e.currentTarget as HTMLElement | null)?.focus();
        }}
        tabIndex={-1}
      >
        <div className="flex items-center gap-3 border-b border-border bg-surface px-5 py-3">
          <div className="min-w-0 flex-1">
            <DialogPrimitive.Title className="flex items-center gap-2">
              <span className="truncate font-mono text-[17px] font-semibold">{d?.key ?? "…"}</span>
              {d && <StatusBadge status={d.status} />}
              {d && d.severity !== "none" && <SeverityBadge severity={d.severity} />}
              {d?.disabled_badge && <DisabledBadge />}
              {d?.matched_by === "content" && (
                <Badge tone="accent"><Link2 /> Matched by content</Badge>
              )}
            </DialogPrimitive.Title>
            {d && (
              <p className="mt-0.5 flex items-center gap-1.5 truncate text-[12.5px] text-muted">
                <span className="font-mono">{d.acl}</span>
                {(d.asa?.source_zone || d.ftd?.source_zone) && <>· zone <span className="font-mono">{d.asa?.source_zone || d.ftd?.source_zone}</span></>}
                {d.asa && d.ftd && d.asa.key !== d.ftd.key && (
                  <>· <span className="font-mono">{d.asa.key}</span><ArrowRight className="h-3 w-3" /><span className="font-mono">{d.ftd.key}</span></>
                )}
              </p>
            )}
          </div>
          <span className="text-[12px] tabular-nums text-muted">{position}</span>
          <Tip content={<>Previous rule <span className="kbd ml-1">K</span></>}>
            <Button variant="ghost" size="icon-sm" onClick={onPrev} aria-label="Previous rule"><ChevronUp /></Button>
          </Tip>
          <Tip content={<>Next rule <span className="kbd ml-1">J</span></>}>
            <Button variant="ghost" size="icon-sm" onClick={onNext} aria-label="Next rule"><ChevronDown /></Button>
          </Tip>
          <DialogPrimitive.Close asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Close (Esc)"><X /></Button>
          </DialogPrimitive.Close>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5 scrollbar-thin">
          {err && <ErrorState message={err} />}
          {!d && !err && (
            <div className="space-y-3">
              <Skeleton className="h-24" />
              <Skeleton className="h-72" />
            </div>
          )}
          {d && (
            <>
              <RiskBox d={d} />
              <div className="flex items-center justify-between">
                <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted">Field comparison</h3>
                <ToggleGroup type="single" value={expanded ? "exp" : "written"} onValueChange={(v) => v && setExpanded(v === "exp")} aria-label="Value view">
                  <ToggleGroupItem value="written">As written</ToggleGroupItem>
                  <ToggleGroupItem value="exp">Expanded</ToggleGroupItem>
                </ToggleGroup>
              </div>
              <FieldTable d={d} expanded={expanded} />
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
                <span className="flex items-center gap-1"><span className="chip chip-removed !py-0">− removed</span> in ASA, not in FTD</span>
                <span className="flex items-center gap-1"><span className="chip chip-added !py-0">+ added</span> in FTD, not in ASA</span>
                <span className="flex items-center gap-1"><span className="pill-any !py-0 text-[11px]">ANY ⚠</span> widened to any</span>
              </div>
              <RawView d={d} />
              {d.asa && (
                <p className="text-[12px] text-muted">
                  ASA line numbers — ACE-only: <span className="font-mono">{d.asa.line_no_ace ?? "—"}</span>, all lines:{" "}
                  <span className="font-mono">{d.asa.line_no_all ?? "—"}</span>
                  {d.ftd?.position != null && <> · FTD global position: <span className="font-mono">{d.ftd.position}</span></>}
                </p>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-4 border-t border-border bg-surface px-5 py-2 text-[12px] text-muted">
          <span><span className="kbd">J</span> / <span className="kbd">K</span> next / previous</span>
          <span><span className="kbd">Esc</span> close</span>
        </div>
      </SheetContent>
    </Dialog>
  );
}
