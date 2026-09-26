import { motion } from "framer-motion";
import { Ban, Check, Circle, Loader2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Mark } from "@/components/common/Brand";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import type { JobSnapshot } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = [
  { id: "asa", label: "Reading ASA config" },
  { id: "objects", label: "Expanding objects" },
  { id: "pdf", label: "Reading PDF" },
  { id: "match", label: "Matching rules" },
  { id: "compare", label: "Comparing" },
  { id: "done", label: "Done" },
];

export default function ProcessingPage() {
  const { jobId = "" } = useParams();
  const nav = useNavigate();
  const [snap, setSnap] = useState<JobSnapshot | null>(null);
  const [lost, setLost] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const t0 = useRef(Date.now());

  useEffect(() => {
    const es = new EventSource(api.jobEventsUrl(jobId));
    es.onmessage = (e) => {
      const s: JobSnapshot = JSON.parse(e.data);
      setSnap(s);
      if (s.state === "done" && s.session_id) {
        es.close();
        setTimeout(() => nav(`/s/${s.session_id}/dashboard`, { replace: true }), 450);
      } else if (s.state === "error" || s.state === "cancelled") {
        es.close();
      }
    };
    es.onerror = () => {
      es.close();
      // Fall back to one status poll (e.g. the job already finished before we connected).
      api
        .job(jobId)
        .then((s) => {
          setSnap(s);
          if (s.state === "done" && s.session_id) nav(`/s/${s.session_id}/dashboard`, { replace: true });
        })
        .catch(() => setLost(true));
    };
    return () => es.close();
  }, [jobId, nav]);

  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - t0.current) / 1000), 250);
    return () => clearInterval(t);
  }, []);

  const current = snap?.step ?? "asa";
  const idx = STEPS.findIndex((s) => s.id === current);
  const c = snap?.counters ?? {};
  const failed = snap?.state === "error";
  const cancelled = snap?.state === "cancelled";
  const pct = c.pages ? Math.round((100 * (c.page ?? 0)) / c.pages) : 0;

  return (
    <div className="flex min-h-full items-center justify-center p-8">
      <div className="card w-full max-w-[640px] p-8">
        <div className="mb-6 flex items-center gap-4">
          <motion.div animate={failed || cancelled ? {} : { scale: [1, 1.06, 1] }} transition={{ repeat: Infinity, duration: 1.6 }}>
            <Mark size={44} />
          </motion.div>
          <div className="flex-1">
            <h1 className="text-lg font-semibold">
              {failed ? "Comparison failed" : cancelled ? "Comparison cancelled" : snap?.state === "done" ? "Comparison complete" : "Comparing…"}
            </h1>
            <p className="text-sm text-muted">{elapsed.toFixed(0)}s elapsed · processing locally on this computer</p>
          </div>
        </div>

        <ol className="space-y-1" aria-label="Progress">
          {STEPS.map((s, i) => {
            const done = snap?.state === "done" || i < idx;
            const active = i === idx && !done && !failed && !cancelled;
            const errored = (failed || cancelled) && i === idx;
            let detail = "";
            if (s.id === "pdf" && c.pages) detail = `page ${fmtInt(c.page)} of ${fmtInt(c.pages)}`;
            if (s.id === "compare" && c.pairs) detail = c.compared ? `${fmtInt(c.compared)} of ${fmtInt(c.pairs)} rules` : `${fmtInt(c.pairs)} rules`;
            return (
              <li key={s.id} className={cn("rounded-input px-3 py-2.5", active && "bg-primary/5")}>
                <div className="flex items-center gap-3">
                  <span className={cn("flex h-6 w-6 items-center justify-center rounded-full border",
                    done ? "border-ok bg-ok text-white" : active ? "border-primary text-primary" : errored ? "border-critical text-critical" : "border-border text-muted/50")}>
                    {done ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : active ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : errored ? <XCircle className="h-4 w-4" /> : <Circle className="h-2 w-2 fill-current" />}
                  </span>
                  <span className={cn("flex-1 text-sm", done ? "text-text" : active ? "font-medium text-text" : "text-muted")}>
                    {s.id === "pdf" && c.pages && (active || done) ? `Reading PDF (page ${fmtInt(c.page)} of ${fmtInt(c.pages)})` : s.label}
                  </span>
                  {detail && s.id !== "pdf" && <span className="font-mono text-[12px] text-muted">{detail}</span>}
                </div>
                {s.id === "pdf" && active && c.pages ? (
                  <div className="ml-9 mt-2 h-1.5 overflow-hidden rounded-full bg-border">
                    <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>

        <dl className="mt-6 grid grid-cols-4 gap-3">
          {[
            ["ASA rules", c.asa_rules],
            ["Objects resolved", c.objects_resolved],
            ["FTD rules", c.ftd_rules],
            ["Pages read", c.page],
          ].map(([label, v]) => (
            <div key={label as string} className="rounded-input border border-border bg-surface-2/50 px-3 py-2">
              <dt className="text-[11px] uppercase tracking-wide text-muted">{label}</dt>
              <dd className="font-mono text-lg font-semibold tabular-nums">{v != null ? fmtInt(v as number) : "—"}</dd>
            </div>
          ))}
        </dl>

        {(failed || lost) && (
          <div role="alert" className="mt-6 flex items-start gap-3 rounded-input border border-critical/40 bg-critical/5 p-3">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-critical" />
            <p className="text-sm">{lost ? "Lost connection to Sibit's local server." : snap?.error}</p>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          {failed || cancelled || lost ? (
            <Button onClick={() => nav("/")}>Back to new comparison</Button>
          ) : (
            <Button variant="secondary" onClick={() => api.cancelJob(jobId).catch(() => undefined)} disabled={snap?.state === "done"}>
              <Ban /> Cancel
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
