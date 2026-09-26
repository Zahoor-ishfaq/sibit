import { ChevronDown, FilterX, Rows2, Rows4, Search, X } from "lucide-react";
import { forwardRef } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/misc";
import { Tip } from "@/components/ui/tooltip";
import { FLAG_LABEL, SEVERITY_LABEL, SEVERITY_ORDER, STATUS_LABEL, STATUS_ORDER, fmtInt } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";
import type { Filters } from "@/lib/types";
import { cn } from "@/lib/utils";

function Facet<T extends string>({
  label,
  options,
  selected,
  onChange,
  render,
  counts,
}: {
  label: string;
  options: T[];
  selected: T[];
  onChange: (v: T[]) => void;
  render?: (v: T) => string;
  counts?: Record<string, number>;
}) {
  const active = selected.length > 0;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary" size="sm" className={cn("gap-1.5", active && "border-primary/50 bg-primary/5 text-text")}>
          {label}
          {active && <span className="rounded bg-primary px-1.5 text-[11px] font-semibold text-white">{selected.length}</span>}
          <ChevronDown className="text-muted" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[14rem]">
        <DropdownMenuLabel>{label}</DropdownMenuLabel>
        {options.map((o) => (
          <DropdownMenuCheckboxItem
            key={o}
            checked={selected.includes(o)}
            onCheckedChange={(c) => onChange(c ? [...selected, o] : selected.filter((x) => x !== o))}
          >
            <span className="flex-1 truncate">{render ? render(o) : o}</span>
            {counts && <span className="ml-3 font-mono text-[11px] text-muted">{fmtInt(counts[o] ?? 0)}</span>}
          </DropdownMenuCheckboxItem>
        ))}
        {active && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => onChange([])}>
              <X /> Clear
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const FiltersBar = forwardRef<
  HTMLInputElement,
  {
    filters: Filters;
    onChange: (f: Filters) => void;
    acls: string[];
    flagTypes: string[];
    counts: { status: Record<string, number>; severity: Record<string, number>; acl: Record<string, number>; flag: Record<string, number> };
    shown: number;
    total: number;
    searching: boolean;
  }
>(({ filters, onChange, acls, flagTypes, counts, shown, total, searching }, ref) => {
  const { density, setDensity } = usePrefs();
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const any =
    filters.status.length || filters.severity.length || filters.acl.length || filters.flag.length || filters.enabled || filters.q;
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-3">
      <div className="relative w-[340px]">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <Input
          ref={ref}
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
          placeholder="Search IP, object, port, comment…"
          className="pl-8 pr-14 font-mono text-[13px]"
          aria-label="Search rules"
        />
        {filters.q ? (
          <button className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted hover:text-text" onClick={() => set({ q: "" })} aria-label="Clear search">
            <X className="h-4 w-4" />
          </button>
        ) : (
          <span className="kbd absolute right-2 top-1/2 -translate-y-1/2">/</span>
        )}
      </div>
      <Facet label="Status" options={STATUS_ORDER} selected={filters.status} onChange={(v) => set({ status: v })} render={(s) => STATUS_LABEL[s]} counts={counts.status} />
      <Facet label="Severity" options={SEVERITY_ORDER.filter((s) => s !== "none")} selected={filters.severity} onChange={(v) => set({ severity: v })}
        render={(s) => SEVERITY_LABEL[s]} counts={counts.severity} />
      <Facet label="ACL / zone" options={acls} selected={filters.acl} onChange={(v) => set({ acl: v })} counts={counts.acl} />
      <Facet label="Flag" options={flagTypes} selected={filters.flag} onChange={(v) => set({ flag: v })} render={(f) => FLAG_LABEL[f] ?? f} counts={counts.flag} />
      <ToggleGroup type="single" value={filters.enabled || "all"} onValueChange={(v) => set({ enabled: v === "all" || !v ? "" : (v as Filters["enabled"]) })} aria-label="Enabled filter">
        <ToggleGroupItem value="all">All</ToggleGroupItem>
        <ToggleGroupItem value="enabled">Enabled</ToggleGroupItem>
        <ToggleGroupItem value="disabled">Disabled</ToggleGroupItem>
      </ToggleGroup>
      {any ? (
        <Button variant="ghost" size="sm" onClick={() => onChange({ status: [], severity: [], acl: [], flag: [], enabled: "", q: "" })}>
          <FilterX /> Clear filters
        </Button>
      ) : null}
      <div className="ml-auto flex items-center gap-3">
        <span className={cn("text-[12.5px] text-muted tabular-nums", searching && "animate-pulse")} aria-live="polite">
          {fmtInt(shown)} of {fmtInt(total)} rules
        </span>
        <ToggleGroup type="single" value={density} onValueChange={(v) => v && setDensity(v as "comfortable" | "compact")} aria-label="Row density">
          <Tip content="Comfortable"><ToggleGroupItem value="comfortable" aria-label="Comfortable"><Rows2 /></ToggleGroupItem></Tip>
          <Tip content="Compact"><ToggleGroupItem value="compact" aria-label="Compact"><Rows4 /></ToggleGroupItem></Tip>
        </ToggleGroup>
      </div>
    </div>
  );
});
FiltersBar.displayName = "FiltersBar";
