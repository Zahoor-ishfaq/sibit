import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DiffDrawer } from "@/components/diff/DiffDrawer";
import { FiltersBar } from "@/components/rules/FiltersBar";
import { RulesTable } from "@/components/rules/RulesTable";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Filters, Row, Severity, Status } from "@/lib/types";
import { isTypingTarget } from "@/lib/utils";

function parseFilters(p: URLSearchParams): Filters {
  const list = (k: string) => (p.get(k) ?? "").split(",").filter(Boolean);
  const en = p.get("enabled");
  return {
    status: list("status") as Status[],
    severity: list("severity") as Severity[],
    acl: list("acl"),
    flag: list("flag"),
    enabled: en === "enabled" || en === "disabled" ? en : "",
    q: p.get("q") ?? "",
  };
}

function toParams(f: Filters, rule: number | null): URLSearchParams {
  const p = new URLSearchParams();
  if (f.status.length) p.set("status", f.status.join(","));
  if (f.severity.length) p.set("severity", f.severity.join(","));
  if (f.acl.length) p.set("acl", f.acl.join(","));
  if (f.flag.length) p.set("flag", f.flag.join(","));
  if (f.enabled) p.set("enabled", f.enabled);
  if (f.q) p.set("q", f.q);
  if (rule != null) p.set("rule", String(rule));
  return p;
}

function facetMatch(r: Row, f: Filters, skip?: keyof Filters): boolean {
  if (skip !== "status" && f.status.length && !f.status.includes(r.status)) return false;
  if (skip !== "severity" && f.severity.length && !f.severity.includes(r.severity)) return false;
  if (skip !== "acl" && f.acl.length && !f.acl.includes(r.acl) && !f.acl.includes(r.zone ?? "")) return false;
  if (skip !== "flag" && f.flag.length && !r.flags.some((x) => f.flag.includes(x))) return false;
  if (skip !== "enabled" && f.enabled === "enabled" && !r.enabled) return false;
  if (skip !== "enabled" && f.enabled === "disabled" && r.enabled) return false;
  return true;
}

export default function RulesPage() {
  const { sid, rows, meta, error, reloadMeta, setLastFilters } = useSession();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(params), [params]);
  const ruleParam = params.get("rule");
  const selected = ruleParam != null && ruleParam !== "" ? Number(ruleParam) : null;
  const searchRef = useRef<HTMLInputElement>(null);
  const [qInput, setQInput] = useState(filters.q);
  const [qIds, setQIds] = useState<Set<number> | null>(null);
  const [searching, setSearching] = useState(false);
  const [order, setOrder] = useState<number[]>([]);

  // Global search runs on the server (IP containment through groups, ports, names, comments).
  useEffect(() => {
    const q = filters.q.trim();
    if (!q) {
      setQIds(null);
      return;
    }
    setSearching(true);
    let alive = true;
    api
      .search(sid, { q })
      .then((r) => alive && setQIds(new Set(r.ids)))
      .catch(() => alive && setQIds(new Set()))
      .finally(() => alive && setSearching(false));
    return () => {
      alive = false;
    };
  }, [sid, filters.q]);

  const update = useCallback(
    (f: Filters, rule: number | null = selected) => setParams(toParams(f, rule), { replace: true }),
    [setParams, selected],
  );

  // Debounce typing into the URL.
  useEffect(() => {
    if (qInput === filters.q) return;
    const t = setTimeout(() => update({ ...filters, q: qInput }), 220);
    return () => clearTimeout(t);
  }, [qInput, filters, update]);
  useEffect(() => setQInput(filters.q), [filters.q]);

  const visible = useMemo(() => {
    if (!rows) return [];
    return rows.filter((r) => facetMatch(r, filters) && (!qIds || qIds.has(r.id)));
  }, [rows, filters, qIds]);

  useEffect(() => {
    if (rows) setLastFilters(filters, visible.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible.length, filters, rows]);

  const counts = useMemo(() => {
    const c = { status: {} as Record<string, number>, severity: {} as Record<string, number>, acl: {} as Record<string, number>, flag: {} as Record<string, number> };
    if (!rows) return c;
    for (const r of rows) {
      if (qIds && !qIds.has(r.id)) continue;
      if (facetMatch(r, filters, "status")) c.status[r.status] = (c.status[r.status] ?? 0) + 1;
      if (facetMatch(r, filters, "severity")) c.severity[r.severity] = (c.severity[r.severity] ?? 0) + 1;
      if (facetMatch(r, filters, "acl")) c.acl[r.acl] = (c.acl[r.acl] ?? 0) + 1;
      if (facetMatch(r, filters, "flag")) for (const f of r.flags) c.flag[f] = (c.flag[f] ?? 0) + 1;
    }
    return c;
  }, [rows, filters, qIds]);

  const select = useCallback((id: number | null) => update(filters, id), [update, filters]);
  const step = useCallback(
    (dir: 1 | -1) => {
      if (!order.length) return;
      const i = selected == null ? -1 : order.indexOf(selected);
      const next = i < 0 ? (dir === 1 ? 0 : order.length - 1) : Math.min(order.length - 1, Math.max(0, i + dir));
      select(order[next]);
    },
    [order, selected, select],
  );

  // Keyboard: J/K next/previous, / focuses search, Esc closes the drawer (handled by the dialog).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isTypingTarget(e.target)) {
        if (e.key === "Escape" && e.target === searchRef.current) searchRef.current?.blur();
        return;
      }
      if (e.key === "j" || e.key === "J") {
        e.preventDefault();
        step(1);
      } else if (e.key === "k" || e.key === "K") {
        e.preventDefault();
        step(-1);
      } else if (e.key === "/") {
        e.preventDefault();
        if (selected != null) select(null);
        setTimeout(() => searchRef.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, select, selected]);

  if (error) return <div className="p-8"><ErrorState message={error} onRetry={reloadMeta} /></div>;

  const pos = selected != null ? order.indexOf(selected) : -1;
  return (
    <div className="flex h-full flex-col">
      <FiltersBar
        ref={searchRef}
        filters={{ ...filters, q: qInput }}
        onChange={(f) => {
          // Search text is debounced into the URL; facet changes apply immediately.
          setQInput(f.q);
          const facets = (x: Filters) => JSON.stringify({ ...x, q: "" });
          if (facets(f) !== facets(filters)) update({ ...f, q: filters.q });
        }}
        acls={meta?.acls ?? []}
        flagTypes={meta?.flag_types ?? []}
        counts={counts}
        shown={visible.length}
        total={rows?.length ?? 0}
        searching={searching}
      />
      {!rows ? (
        <TableSkeleton />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No rules match these filters"
          action={<Button variant="secondary" size="sm" onClick={() => { setQInput(""); update({ status: [], severity: [], acl: [], flag: [], enabled: "", q: "" }, null); }}>Clear filters</Button>}
        >
          {filters.q ? <>Nothing touches <span className="font-mono">{filters.q}</span> with the current filters.</> : "Try removing a filter."}
        </EmptyState>
      ) : (
        <RulesTable rows={visible} selectedId={selected} onSelect={(id) => select(id)} onOrderChange={setOrder} />
      )}
      <DiffDrawer
        sid={sid}
        id={selected}
        onClose={() => select(null)}
        onPrev={() => step(-1)}
        onNext={() => step(1)}
        position={pos >= 0 ? `${fmtInt(pos + 1)} / ${fmtInt(order.length)}` : ""}
      />
    </div>
  );
}
