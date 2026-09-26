import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ChevronsUpDown, Link2, PowerOff, TriangleAlert } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Tip } from "@/components/ui/tooltip";
import { SEVERITY_RANK, STATUS_ORDER } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";
import type { Row } from "@/lib/types";
import { cn } from "@/lib/utils";
import { FlagChip, SeverityBadge, StatusBadge } from "./Badges";

const col = createColumnHelper<Row>();

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

// Address/service/flag columns share the remaining width; the rest are fixed.
const FLEX = new Set(["src", "dst", "services", "flags"]);
function colStyle(id: string, size: number): CSSProperties {
  return FLEX.has(id) ? { flex: `${size} 1 0`, minWidth: Math.round(size * 0.45) } : { width: size, flex: "none" };
}

function AddrCell({ text, any, widened }: { text: string; any: boolean; widened: boolean }) {
  if (any && widened)
    return (
      <span className="pill-any !py-0 text-[11px]" aria-label="Widened to ANY">
        ANY <TriangleAlert className="h-3 w-3" />
      </span>
    );
  return <span className={cn("truncate font-mono text-[12.5px]", any && "text-muted")}>{text || "—"}</span>;
}

const columns = [
  col.accessor("status", {
    header: "Status",
    size: 132,
    sortingFn: (a, b) => STATUS_ORDER.indexOf(a.original.status) - STATUS_ORDER.indexOf(b.original.status),
    cell: (c) => <StatusBadge status={c.getValue()} />,
  }),
  col.accessor("severity", {
    header: "Severity",
    size: 96,
    sortingFn: (a, b) => SEVERITY_RANK[a.original.severity] - SEVERITY_RANK[b.original.severity],
    sortDescFirst: true,
    cell: (c) => <SeverityBadge severity={c.getValue()} />,
  }),
  col.accessor("key", {
    header: "Key",
    size: 162,
    sortingFn: (a, b) => a.original.key.localeCompare(b.original.key, undefined, { numeric: true }),
    cell: (c) => (
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="truncate font-mono text-[12.5px] font-medium">{c.getValue()}</span>
        {c.row.original.matched_by === "content" && (
          <Tip content="Matched by content (the FTD name did not map to this ASA line)">
            <Link2 className="h-3.5 w-3.5 shrink-0 text-accent" aria-label="Matched by content" />
          </Tip>
        )}
      </span>
    ),
  }),
  col.accessor("acl", { header: "ACL", size: 104, cell: (c) => <span className="truncate font-mono text-[12px] text-muted">{c.getValue()}</span> }),
  col.accessor("action", {
    header: "Action",
    size: 74,
    cell: (c) => {
      const r = c.row.original;
      const deny = r.action === "deny";
      return (
        <span className={cn("inline-flex items-center gap-1 text-[12.5px] font-medium", deny ? "text-critical" : "text-text")}>
          <span className={cn("h-1.5 w-1.5 rounded-full", deny ? "bg-critical" : "bg-ok")} aria-hidden />
          {cap(r.action_text || r.action)}
        </span>
      );
    },
  }),
  col.accessor("src", {
    header: "Source",
    size: 200,
    enableSorting: false,
    cell: (c) => <AddrCell text={c.getValue()} any={c.row.original.src_any} widened={c.row.original.flags.includes("SRC_WIDENED_TO_ANY")} />,
  }),
  col.accessor("dst", {
    header: "Destination",
    size: 200,
    enableSorting: false,
    cell: (c) => <AddrCell text={c.getValue()} any={c.row.original.dst_any} widened={c.row.original.flags.includes("DST_WIDENED_TO_ANY")} />,
  }),
  col.accessor("services", {
    header: "Services",
    size: 170,
    enableSorting: false,
    cell: (c) => <span className="truncate font-mono text-[12.5px]">{c.getValue() || "—"}</span>,
  }),
  col.accessor("enabled", {
    header: "Enabled",
    size: 70,
    cell: (c) =>
      c.getValue() ? (
        <span className="text-[12.5px] text-muted">Yes</span>
      ) : (
        <span className="inline-flex items-center gap-1 text-[12.5px] text-muted">
          <PowerOff className="h-3.5 w-3.5" /> No
        </span>
      ),
  }),
  col.accessor("flags", {
    header: "Flags",
    size: 260,
    enableSorting: false,
    cell: (c) => {
      const f = c.getValue();
      return (
        <span className="flex min-w-0 items-center gap-1 overflow-hidden">
          {f.slice(0, 2).map((x) => <FlagChip key={x} code={x} />)}
          {f.length > 2 && <span className="text-[11px] text-muted">+{f.length - 2}</span>}
        </span>
      );
    },
  }),
];

export const RulesTable = memo(function RulesTable({
  rows,
  selectedId,
  onSelect,
  onOrderChange,
}: {
  rows: Row[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onOrderChange: (ids: number[]) => void;
}) {
  const { density } = usePrefs();
  const rowH = density === "compact" ? 30 : 40;
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (r) => String(r.id),
  });
  const model = table.getRowModel().rows;
  const ordered = useMemo(() => model.map((r) => r.original.id), [model]);
  useEffect(() => onOrderChange(ordered), [ordered, onOrderChange]);

  const parent = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({ count: model.length, getScrollElement: () => parent.current, estimateSize: () => rowH, overscan: 16 });
  useEffect(() => virt.measure(), [rowH, virt]);

  // Keep the selected row visible during J/K navigation.
  useEffect(() => {
    if (selectedId == null) return;
    const i = ordered.indexOf(selectedId);
    if (i >= 0) virt.scrollToIndex(i, { align: "auto" });
  }, [selectedId, ordered, virt]);

  const width = table.getFlatHeaders().reduce((a, h) => a + (FLEX.has(h.column.id) ? Math.round(h.getSize() * 0.45) : h.getSize()), 0);
  return (
    <div ref={parent} className="relative min-h-0 flex-1 overflow-auto scrollbar-thin" role="grid" aria-rowcount={model.length}>
      <div style={{ minWidth: width }} className="sticky top-0 z-10 flex border-b border-border bg-surface-2/95 backdrop-blur" role="row">
        {table.getFlatHeaders().map((h) => {
          const sorted = h.column.getIsSorted();
          const can = h.column.getCanSort();
          return (
            <div key={h.id} style={colStyle(h.column.id, h.getSize())} role="columnheader"
              aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}>
              <button
                disabled={!can}
                onClick={h.column.getToggleSortingHandler()}
                className={cn("flex h-9 w-full items-center gap-1 px-3 text-left text-[11.5px] font-semibold uppercase tracking-wide text-muted", can && "hover:text-text")}
              >
                {flexRender(h.column.columnDef.header, h.getContext())}
                {can && (sorted === "asc" ? <ArrowUp className="h-3 w-3" /> : sorted === "desc" ? <ArrowDown className="h-3 w-3" /> : <ChevronsUpDown className="h-3 w-3 opacity-40" />)}
              </button>
            </div>
          );
        })}
      </div>
      <div style={{ height: virt.getTotalSize(), minWidth: width, position: "relative" }}>
        {virt.getVirtualItems().map((v) => {
          const row = model[v.index];
          const r = row.original;
          const sel = r.id === selectedId;
          return (
            <div
              key={row.id}
              role="row"
              aria-selected={sel}
              tabIndex={-1}
              onClick={() => onSelect(r.id)}
              className={cn(
                "absolute left-0 flex w-full cursor-pointer items-center border-b border-border/70 transition-colors",
                sel ? "bg-primary/10 shadow-[inset_3px_0_0_rgb(var(--primary))]" : "hover:bg-surface-2/70",
                r.severity === "critical" && !sel && "shadow-[inset_3px_0_0_rgb(var(--critical))]",
                !r.enabled && "opacity-75",
              )}
              style={{ height: rowH, transform: `translateY(${v.start}px)` }}
            >
              {row.getVisibleCells().map((cell) => (
                <div key={cell.id} role="gridcell" className="flex min-w-0 items-center overflow-hidden px-3"
                  style={colStyle(cell.column.id, cell.column.getSize())}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
});
