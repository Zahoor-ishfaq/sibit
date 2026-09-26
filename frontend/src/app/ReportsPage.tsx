import { Braces, Download, FileSpreadsheet, FileText, Filter, FolderDown, Save } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useToast } from "@/components/common/Toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { FLAG_LABEL, SEVERITY_LABEL, STATUS_LABEL, fmtInt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Filters } from "@/lib/types";
import { download } from "@/lib/utils";

function describe(f: Filters): string[] {
  const out: string[] = [];
  if (f.status.length) out.push(`Status: ${f.status.map((s) => STATUS_LABEL[s]).join(", ")}`);
  if (f.severity.length) out.push(`Severity: ${f.severity.map((s) => SEVERITY_LABEL[s]).join(", ")}`);
  if (f.acl.length) out.push(`ACL: ${f.acl.join(", ")}`);
  if (f.flag.length) out.push(`Flag: ${f.flag.map((x) => FLAG_LABEL[x] ?? x).join(", ")}`);
  if (f.enabled) out.push(f.enabled === "enabled" ? "Enabled only" : "Disabled only");
  if (f.q) out.push(`Search: "${f.q}"`);
  return out;
}

const FORMATS = [
  { id: "xlsx", label: "Excel report", ext: ".xlsx", icon: FileSpreadsheet, desc: "Summary, All Rules, Critical & High, Changed, Missing, Extra, Order Changes and Unresolved Objects sheets — frozen headers, filters, severity colours and red/green diff cells." },
  { id: "csv", label: "CSV", ext: ".csv", icon: FileText, desc: "One row per rule pair with ASA and FTD columns side by side, expanded values and diff text. UTF-8, opens in Excel." },
  { id: "json", label: "JSON", ext: ".json", icon: Braces, desc: "Full machine-readable result: every rule pair with field diffs, flags, explanations, order changes and warnings." },
] as const;

export default function ReportsPage() {
  const { sid, meta, lastFilters, lastFilteredCount, reloadMeta } = useSession();
  const toast = useToast();
  const hasFilter = !!lastFilters && describe(lastFilters).length > 0;
  const [filtered, setFiltered] = useState(false);
  const useFilter = filtered && hasFilter;

  const save = async () => {
    try {
      const r = await api.save(sid, meta?.name);
      toast({ title: "Project saved", description: r.path, tone: "ok" });
      reloadMeta();
    } catch (e) {
      toast({ title: "Could not save project", description: (e as Error).message, tone: "critical" });
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-lg font-semibold">Reports</h1>
        <p className="text-sm text-muted">Export the comparison for review, tickets or audit. Nothing is uploaded anywhere — files are generated locally.</p>
      </div>

      <section className="card p-5">
        <div className="flex items-start gap-4">
          <Filter className="mt-0.5 h-5 w-5 text-primary" />
          <div className="flex-1 space-y-1">
            <p className="font-medium">Export only the current filtered view</p>
            {hasFilter ? (
              <>
                <p className="text-sm text-muted">
                  The Rules screen is filtered to <b className="text-text">{fmtInt(lastFilteredCount)}</b> of {fmtInt(meta?.counts.total)} rules:
                </p>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {describe(lastFilters!).map((d) => <Badge key={d} tone="primary">{d}</Badge>)}
                </div>
              </>
            ) : (
              <p className="text-sm text-muted">
                No filter is active. Set filters on the <Link className="text-primary hover:underline" to={`/s/${sid}/rules`}>Rules</Link> screen, then come back to export just that view.
              </p>
            )}
          </div>
          <Switch checked={useFilter} onCheckedChange={setFiltered} disabled={!hasFilter} aria-label="Export filtered view only" />
        </div>
      </section>

      <div className="grid grid-cols-3 gap-4">
        {FORMATS.map((f) => (
          <section key={f.id} className="card flex flex-col p-5">
            <f.icon className="mb-3 h-7 w-7 text-primary" />
            <h2 className="font-semibold">{f.label} <span className="font-mono text-[12px] font-normal text-muted">{f.ext}</span></h2>
            <p className="mt-1 flex-1 text-[13px] text-muted">{f.desc}</p>
            <Button className="mt-4" variant={f.id === "xlsx" ? "default" : "secondary"}
              onClick={() => download(api.exportUrl(sid, f.id, useFilter ? lastFilters! : undefined))}>
              <Download /> {useFilter ? `Export ${fmtInt(lastFilteredCount)} rules` : "Export all rules"}
            </Button>
          </section>
        ))}
      </div>

      <section className="card p-5">
        <div className="flex items-start gap-4">
          <FolderDown className="mt-0.5 h-5 w-5 text-primary" />
          <div className="flex-1">
            <p className="font-medium">Project file (.sibit)</p>
            <p className="text-sm text-muted">
              Save the whole comparison to reopen it later without the original files (a zip of JSON + Parquet).
              {meta?.saved_path && <> Saved at <span className="break-all font-mono text-[12px]">{meta.saved_path}</span>.</>}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => download(api.projectUrl(sid))}><Download /> Download .sibit</Button>
            <Button onClick={save}><Save /> Save to Documents\Sibit</Button>
          </div>
        </div>
      </section>
    </div>
  );
}
