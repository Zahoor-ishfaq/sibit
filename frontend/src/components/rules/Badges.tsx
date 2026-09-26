import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  GitMerge,
  Info,
  MinusCircle,
  PencilLine,
  PlusCircle,
  PowerOff,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tip } from "@/components/ui/tooltip";
import { FLAG_LABEL, SEVERITY_LABEL, STATUS_LABEL } from "@/lib/format";
import type { Severity, Status } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { Chip } from "@/lib/format";

const STATUS_TONE: Record<Status, "ok" | "accent" | "medium" | "critical" | "primary" | "neutral"> = {
  MATCH: "ok",
  MATCH_MERGED: "accent",
  CHANGED: "medium",
  MISSING_IN_FTD: "critical",
  EXTRA_IN_FTD: "primary",
  UNRESOLVED: "neutral",
};
const STATUS_ICON = {
  MATCH: CheckCircle2,
  MATCH_MERGED: GitMerge,
  CHANGED: PencilLine,
  MISSING_IN_FTD: MinusCircle,
  EXTRA_IN_FTD: PlusCircle,
  UNRESOLVED: CircleHelp,
} as const;

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const Icon = STATUS_ICON[status];
  return (
    <Badge tone={STATUS_TONE[status]} className={className}>
      <Icon aria-hidden />
      {STATUS_LABEL[status]}
    </Badge>
  );
}

const SEV_ICON = { critical: ShieldAlert, high: AlertTriangle, medium: AlertCircle, low: Info } as const;

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  if (severity === "none") return <span className="text-muted/60" aria-label="No risk">—</span>;
  const Icon = SEV_ICON[severity];
  return (
    <Badge tone={severity} className={cn(severity === "critical" && "font-semibold", className)}>
      <Icon aria-hidden />
      {SEVERITY_LABEL[severity]}
    </Badge>
  );
}

export const FLAG_SEVERITY: Record<string, Severity> = {
  DST_WIDENED_TO_ANY: "critical",
  SRC_WIDENED_TO_ANY: "critical",
  DENY_BECAME_PERMIT: "critical",
  SCOPE_WIDENED: "high",
  DISABLED_BECAME_ENABLED: "high",
  ANY_ANY_PERMIT: "high",
  DENY_SCOPE_NARROWED: "high",
  SCOPE_NARROWED: "medium",
  MISSING_IN_FTD: "medium",
  ENABLED_BECAME_DISABLED: "medium",
  PERMIT_BECAME_DENY: "medium",
  ACTION_CHANGED: "medium",
  DENY_SCOPE_WIDENED: "medium",
  EXTRA_IN_FTD: "medium",
  UNRESOLVED_OBJECTS: "medium",
  SPLIT_IN_FTD: "none",
  LOGGING_CHANGED: "low",
  COMMENT_CHANGED: "low",
};

export function FlagChip({ code, severity, title }: { code: string; severity?: Severity; title?: string }) {
  const sev = severity ?? FLAG_SEVERITY[code] ?? "low";
  // 'info' flags (e.g. SPLIT_IN_FTD) explain a rule without adding risk.
  const tone = sev === "none" || (sev as string) === "info" ? "neutral" : sev;
  return (
    <Tip content={title}>
      <Badge tone={tone} className="font-mono text-[11px] tracking-tight">
        {sev === "critical" && <TriangleAlert aria-hidden />}
        {FLAG_LABEL[code] ?? code}
      </Badge>
    </Tip>
  );
}

export function DisabledBadge() {
  return (
    <Badge tone="neutral">
      <PowerOff aria-hidden /> Disabled
    </Badge>
  );
}

/** A value chip with diff semantics: removed = red strikethrough + '−', added = green '+', any = red pill 'ANY ⚠'. */
export function ValueChip({ chip }: { chip: Chip }) {
  if (chip.kind === "any") {
    return (
      <span className="pill-any" aria-label="Widened to ANY">
        ANY <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
      </span>
    );
  }
  if (chip.kind === "removed") {
    return (
      <span className="chip chip-removed" title="Removed: in ASA, not in FTD">
        <span aria-hidden className="no-underline">−</span>
        <span className="sr-only">removed </span>
        <span className="truncate">{chip.text}</span>
      </span>
    );
  }
  if (chip.kind === "added") {
    return (
      <span className="chip chip-added" title="Added: in FTD, not in ASA">
        <span aria-hidden>+</span>
        <span className="sr-only">added </span>
        <span className="truncate">{chip.text}</span>
      </span>
    );
  }
  return (
    <span className="chip chip-neutral">
      <span className="truncate">{chip.text}</span>
    </span>
  );
}
