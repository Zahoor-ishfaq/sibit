export type Status = "MATCH" | "MATCH_MERGED" | "CHANGED" | "MISSING_IN_FTD" | "EXTRA_IN_FTD" | "UNRESOLVED";
export type Severity = "critical" | "high" | "medium" | "low" | "none";
export type Numbering = "auto" | "ace_only" | "all_lines";

export interface Row {
  id: number;
  status: Status;
  severity: Severity;
  key: string;
  acl: string;
  zone: string | null;
  action: string;
  action_text: string;
  src: string;
  dst: string;
  services: string;
  src_any: boolean;
  dst_any: boolean;
  enabled: boolean;
  asa_enabled: boolean | null;
  ftd_enabled: boolean | null;
  flags: string[];
  matched_by: "name" | "content" | null;
  asa_key: string | null;
  ftd_key: string | null;
  asa_line: number | null;
  ftd_position: number | null;
  changed_fields: string[];
}

export interface RuleSide {
  side: "ASA" | "FTD";
  uid: string;
  key: string;
  acl: string;
  line_no: number;
  line_no_ace: number | null;
  line_no_all: number | null;
  position: number | null;
  source_zone: string | null;
  dest_zone: string | null;
  action: string;
  action_text: string;
  enabled: boolean;
  log: boolean;
  comment: string;
  raw_text: string;
  src_refs: string[];
  dst_refs: string[];
  svc_refs: string[];
  src: string[];
  dst: string[];
  services: string[];
  src_any: boolean;
  dst_any: boolean;
  svc_any: boolean;
  unresolved: string[];
  ref_names: string[];
}

export type FieldName = "action" | "enabled" | "src" | "dst" | "services" | "log" | "comment";

export interface FieldDiff {
  field: FieldName;
  asa: string[];
  ftd: string[];
  asa_expanded: string[];
  ftd_expanded: string[];
  removed: string[];
  added: string[];
  changed: boolean;
  ignored: boolean;
}

export interface Flag {
  code: string;
  severity: Severity;
  message: string;
}

export interface Detail {
  id: number;
  key: string;
  acl: string;
  status: Status;
  severity: Severity;
  matched_by: "name" | "content" | null;
  flags: Flag[];
  diffs: Record<FieldName, FieldDiff>;
  notes: string[];
  explanation: string;
  disabled_badge: boolean;
  asa: RuleSide | null;
  ftd: RuleSide | null;
}

export interface AclCount {
  acl: string;
  total: number;
  critical: number;
  MATCH: number;
  MATCH_MERGED: number;
  CHANGED: number;
  MISSING_IN_FTD: number;
  EXTRA_IN_FTD: number;
  UNRESOLVED: number;
}

export interface Calibration {
  requested: string;
  strategy: string;
  match_rate: number;
  matched_by_name: number;
  matched_by_content: number;
  asa_rules: number;
  acls: {
    acl: string;
    strategy: string;
    scores: Record<string, number>;
    sample: number;
    matched_by_name: number;
    matched_by_content: number;
    asa_rules: number;
    ftd_rules: number;
  }[];
}

export interface Meta {
  id: string;
  name: string;
  asa_name: string;
  ftd_name: string;
  created: string;
  options: { numbering: Numbering; include_disabled: boolean; ignore_comments: boolean };
  asa_summary: Record<string, any>;
  ftd_summary: Record<string, any>;
  seconds: Record<string, number>;
  calibration: Calibration;
  counts: { total: number; status: Record<Status, number>; severity: Record<Severity, number> };
  per_acl: AclCount[];
  order_change_count: number;
  excluded_disabled: number;
  acls: string[];
  zones: string[];
  flag_types: string[];
  top_risks: Row[];
  warning_count: number;
  unresolved_count: number;
  saved_path: string | null;
}

export interface ParseWarning {
  source: "ASA" | "FTD";
  line: number | null;
  text: string;
  message: string;
}

export interface UnresolvedRef {
  side: "ASA" | "FTD";
  name: string;
  reason: string;
  used_by: number[];
}

export interface OrderChange {
  acl: string;
  rule_id: number;
  rule_key: string;
  deny_id: number;
  deny_key: string;
  asa_relation: "above" | "below";
  ftd_relation: "above" | "below";
  asa_rule_line: number;
  asa_deny_line: number;
  ftd_rule_position: number;
  ftd_deny_position: number;
}

export interface ObjectSummary {
  side: "ASA" | "FTD";
  name: string;
  kind: string;
  expanded_count: number;
  used_count: number;
  unresolved: string[];
}

export interface ObjectDetail {
  side: "ASA" | "FTD";
  name: string;
  kind: string;
  line: number | null;
  members: { text: string; ref: string | null; exists: boolean }[];
  expanded: string[];
  unresolved: string[];
  used_by_rules: { id: number; key: string; status: Status; severity: Severity }[];
}

export interface Detect {
  ok: boolean;
  label: string | null;
  error?: string;
  pages?: number;
  version?: string | null;
  policy?: string | null;
  hostname?: string | null;
  sheets?: string[];
}

export interface UploadInfo {
  id: string;
  kind: "asa" | "ftd" | "hits";
  name: string;
  size: number;
  detect: Detect;
}

export interface JobSnapshot {
  id: string;
  state: "queued" | "running" | "done" | "error" | "cancelled";
  step: string;
  counters: Record<string, number>;
  error: string | null;
  session_id: string | null;
  elapsed: number;
  steps: { id: string; label: string }[];
}

export interface RecentProject {
  path: string;
  name: string;
  asa_name: string;
  ftd_name: string;
  saved: string;
  total: number;
  critical: number;
}

export interface Settings {
  theme: "dark" | "light" | "system";
  density: "comfortable" | "compact";
  numbering_default: Numbering;
  include_disabled: boolean;
  ignore_comments: boolean;
  port_overrides: Record<string, number>;
}

export interface Filters {
  status: Status[];
  severity: Severity[];
  acl: string[];
  flag: string[];
  enabled: "" | "enabled" | "disabled";
  q: string;
}

// ---------------------------------------------------------------- hit counts
export type HitVerdict = "GARBAGE" | "IN_USE" | "NO_DATA";

export interface HitMeta {
  id: string;
  file_name: string;
  sheets: string[];
  rows_read: number;
  rows_used: number;
  lines: number;
  rules: number;
  counts: Record<HitVerdict, number>;
  by_sheet: ({ sheet: string } & Record<HitVerdict, number>)[];
  seconds: number;
  warning_count: number;
  partial: number;
  unnamed: number;
}

export interface HitRuleRow {
  id: number;
  verdict: HitVerdict;
  name: string;
  named: boolean;
  rule_id: string | null;
  acl: string | null;
  acl_line: number | null;
  action: string | null;
  lines: number;
  total_hits: number;
  hit_values: number;
  elements: number;
  zero_elements: number;
  sheet: string;
  row: number;
}

export interface HitLineItem {
  sheet: string;
  row: number;
  hit_sum: number;
  hit_n: number;
  hits: number[] | null;
  kind: "summary" | "element" | "table";
  hash: string | null;
  text: string;
}

export interface HitRuleDetail extends HitRuleRow {
  line_items: HitLineItem[];
  truncated: boolean;
}
