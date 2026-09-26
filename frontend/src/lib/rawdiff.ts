import type { Detail, FieldName } from "./types";

export interface Token {
  text: string;
  mark: "none" | "removed" | "added";
}

const FTD_LABELS: Record<FieldName, string[]> = {
  action: ["Action"],
  enabled: [],
  src: ["Source Networks"],
  dst: ["Destination Networks"],
  services: ["Source Ports", "Destination Ports"],
  log: ["Log at Beginning of Connection", "Log at End of Connection"],
  comment: ["Comments"],
};

const ALL_LABELS = [
  "Action", "Source Zones", "Destination Zones", "Source Tunnels", "Source Networks", "Original Client Networks",
  "Destination Networks", "Source Dynamic Attributes", "Destination Dynamic Attributes", "Safe Search", "Youtube EDU",
  "VLAN Tags", "Users", "Applications", "Application Filters", "Source Ports", "Destination Ports", "Source ISE Metadata",
  "Destination ISE Metadata", "Security Group Tag", "Time Range", "URLs", "Intrusion Policy", "Variable Set", "File Policy",
  "Log at Beginning of Connection", "Log at End of Connection", "Log File Events", "Send Events to Defense Center",
  "Send using specific syslog alert", "Send using specific SNMP alert", "Comments",
].sort((a, b) => b.length - a.length);

function changedFields(d: Detail): Set<FieldName> {
  return new Set(
    (Object.values(d.diffs) as { field: FieldName; changed: boolean; ignored: boolean }[])
      .filter((x) => x.changed && !x.ignored)
      .map((x) => x.field),
  );
}

/** Tokens of the ASA access-list line, with tokens belonging to changed fields marked 'removed'. */
export function asaTokens(d: Detail): Token[] {
  const raw = d.asa?.raw_text ?? "";
  if (!d.asa || !d.ftd) return raw.split(/(\s+)/).map((t) => ({ text: t, mark: "none" }));
  const ch = changedFields(d);
  const hot = new Set<string>();
  const add = (refs: string[]) => refs.forEach((r) => r.split(/\s+/).forEach((t) => hot.add(t)));
  if (ch.has("src")) add(d.asa.src_refs);
  if (ch.has("dst")) add(d.asa.dst_refs);
  if (ch.has("services")) add(d.asa.svc_refs.map((s) => s.replace(/^(tcp|udp|tcp-udp|icmp|ip)\s+(src\s+)?/, "")));
  if (ch.has("action")) ["permit", "deny"].forEach((t) => hot.add(t));
  if (ch.has("enabled")) hot.add("inactive");
  if (ch.has("log")) hot.add("log");
  // Never mark the ACL keyword scaffolding.
  for (const t of ["access-list", "extended", "object", "object-group", "host", "eq", "range", "any", "any4", "any6"]) hot.delete(t);
  return raw.split(/(\s+)/).map((t) => ({ text: t, mark: hot.has(t) ? "removed" : "none" }));
}

export interface FtdLine {
  text: string;
  mark: "none" | "added";
}

/** Lines of the FTD rule block, with the lines of changed fields marked 'added'. */
export function ftdLines(d: Detail): FtdLine[] {
  const raw = d.ftd?.raw_text ?? "";
  const lines = raw.split("\n");
  if (!d.asa || !d.ftd) return lines.map((text) => ({ text, mark: "none" }));
  const ch = changedFields(d);
  const hotLabels = new Set<string>();
  for (const f of ch) FTD_LABELS[f].forEach((l) => hotLabels.add(l));
  let current: string | null = null;
  return lines.map((text, i) => {
    if (i === 0) return { text, mark: ch.has("enabled") ? "added" : "none" };
    const label = ALL_LABELS.find((l) => text === l || text.startsWith(l + " "));
    if (label) current = label;
    return { text, mark: current && hotLabels.has(current) ? "added" : "none" };
  });
}
