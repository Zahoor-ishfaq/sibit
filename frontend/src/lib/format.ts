import type { Detail, FieldDiff, Severity, Status } from "./types";

export const STATUS_ORDER: Status[] = ["MATCH", "MATCH_MERGED", "CHANGED", "MISSING_IN_FTD", "EXTRA_IN_FTD", "UNRESOLVED"];
export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "none"];
export const SEVERITY_RANK: Record<Severity, number> = { critical: 4, high: 3, medium: 2, low: 1, none: 0 };

export const STATUS_LABEL: Record<Status, string> = {
  MATCH: "Match",
  MATCH_MERGED: "Match (merged)",
  CHANGED: "Changed",
  MISSING_IN_FTD: "Missing in FTD",
  EXTRA_IN_FTD: "Extra in FTD",
  UNRESOLVED: "Unresolved",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "—",
};

export const FLAG_LABEL: Record<string, string> = {
  DST_WIDENED_TO_ANY: "Destination → ANY",
  SRC_WIDENED_TO_ANY: "Source → ANY",
  DENY_BECAME_PERMIT: "Deny → Permit",
  SCOPE_WIDENED: "Scope widened",
  DISABLED_BECAME_ENABLED: "Disabled → Enabled",
  ANY_ANY_PERMIT: "Any → Any permit",
  SCOPE_NARROWED: "Scope narrowed",
  MISSING_IN_FTD: "Missing in FTD",
  ENABLED_BECAME_DISABLED: "Enabled → Disabled",
  LOGGING_CHANGED: "Logging changed",
  COMMENT_CHANGED: "Comment changed",
  PERMIT_BECAME_DENY: "Permit → Deny",
  ACTION_CHANGED: "Action changed",
  DENY_SCOPE_NARROWED: "Deny narrowed",
  DENY_SCOPE_WIDENED: "Deny widened",
  EXTRA_IN_FTD: "Extra in FTD",
  UNRESOLVED_OBJECTS: "Unresolved objects",
  SPLIT_IN_FTD: "Split in FTD",
};

export const FIELD_LABEL: Record<string, string> = {
  action: "Action",
  enabled: "Enabled",
  src: "Source",
  dst: "Destination",
  services: "Services",
  log: "Logging",
  comment: "Comment",
};

export const NUMBERING_LABEL: Record<string, string> = {
  auto: "Auto",
  ace_only: "ACE-only",
  all_lines: "All lines",
};

export function fmtInt(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("en-US");
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

export function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export type ChipKind = "neutral" | "removed" | "added" | "any";

export interface Chip {
  text: string;
  kind: ChipKind;
}

/**
 * Chips for one side of a field in the diff drawer.
 * Removed (ASA only) → red + strikethrough; Added (FTD only) → green '+';
 * widened to any → 'ANY ⚠' pill, with every ASA value shown as removed.
 */
export function fieldChips(d: FieldDiff, side: "asa" | "ftd", expanded: boolean, detail: Detail): Chip[] {
  const values = expanded ? (side === "asa" ? d.asa_expanded : d.ftd_expanded) : side === "asa" ? d.asa : d.ftd;
  const active = d.changed && !d.ignored;
  const addrField = d.field === "src" || d.field === "dst";
  const asaAny = addrField && (d.field === "src" ? detail.asa?.src_any : detail.asa?.dst_any);
  const ftdAny = addrField && (d.field === "src" ? detail.ftd?.src_any : detail.ftd?.dst_any);
  const widenedToAny = active && addrField && !!ftdAny && !asaAny && !!detail.asa && !!detail.ftd;

  if (side === "ftd" && widenedToAny) return [{ text: "ANY", kind: "any" }];
  if (!active || !detail.asa || !detail.ftd) return values.map((text) => ({ text, kind: "neutral" }));
  if (side === "asa" && widenedToAny) return values.map((text) => ({ text, kind: "removed" }));

  if (d.field === "action" || d.field === "enabled" || d.field === "log" || d.field === "comment") {
    return values.map((text) => ({ text, kind: side === "asa" ? "removed" : "added" }));
  }
  if (!expanded) return values.map((text) => ({ text, kind: "neutral" }));
  const marked = new Set(side === "asa" ? d.removed : d.added);
  const out: Chip[] = values.map((text) => ({ text, kind: marked.has(text) ? (side === "asa" ? "removed" : "added") : "neutral" }));
  // Items only expressible as a difference (e.g. 'TCP 8011-8020') are appended.
  const present = new Set(values);
  for (const m of marked) if (!present.has(m)) out.push({ text: m, kind: side === "asa" ? "removed" : "added" });
  return out;
}

/** Plain-text summary for "Copy finding" (ticket-ready). */
export function findingText(d: Detail): string {
  const lines: string[] = [];
  lines.push(`[Sibit] ${d.key} — ${STATUS_LABEL[d.status]}${d.severity !== "none" ? ` / ${SEVERITY_LABEL[d.severity]}` : ""}`);
  if (d.flags.length) lines.push(`Flags: ${d.flags.map((f) => f.code).join(", ")}`);
  if (d.matched_by === "content") lines.push("Matched by content (FTD name did not map to the ASA line).");
  lines.push("");
  lines.push(d.explanation);
  for (const n of d.notes) lines.push(`- ${n}`);
  lines.push("");
  const side = (label: string, r: Detail["asa"]) => {
    if (!r) {
      lines.push(`${label}: (none)`);
      return;
    }
    lines.push(`${label}: ${r.key}${r.position ? ` (position ${r.position})` : ""}${r.enabled ? "" : " [disabled]"}`);
    lines.push(`  Action:      ${r.action_text || r.action}`);
    lines.push(`  Source:      ${r.src_refs.join(", ")}${sameList(r.src_refs, r.src) ? "" : `  = ${r.src.join(", ")}`}`);
    lines.push(`  Destination: ${r.dst_refs.join(", ")}${sameList(r.dst_refs, r.dst) ? "" : `  = ${r.dst.join(", ")}`}`);
    lines.push(`  Services:    ${r.svc_refs.join(", ")}${sameList(r.svc_refs, r.services) ? "" : `  = ${r.services.join(", ")}`}`);
  };
  side("ASA (before)", d.asa);
  side("FTD (after)", d.ftd);
  if (d.asa && d.ftd) {
    const changed = Object.values(d.diffs).filter((x) => x.changed && !x.ignored);
    if (changed.length) {
      lines.push("");
      lines.push("Differences:");
      for (const c of changed) {
        const parts = [...c.removed.map((x) => `- ${x}`), ...c.added.map((x) => `+ ${x}`)];
        const addr = c.field === "src" || c.field === "dst";
        const widened = addr && (c.field === "src" ? d.ftd.src_any && !d.asa.src_any : d.ftd.dst_any && !d.asa.dst_any);
        const text = widened ? [...c.asa_expanded.map((x) => `- ${x}`), "+ ANY"].join(", ") : parts.join(", ");
        lines.push(`  ${FIELD_LABEL[c.field]}: ${text}`);
      }
    }
  }
  return lines.join("\n");
}

function sameList(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i]);
}

export function shortId(key: string): string {
  const m = key.match(/_#(\d+)$/);
  return m ? `#${m[1]}` : key;
}
