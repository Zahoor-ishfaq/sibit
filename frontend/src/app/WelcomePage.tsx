import {
  CheckCircle2,
  ChevronDown,
  FileCode2,
  FileText,
  FolderOpen,
  Loader2,
  Lock,
  SlidersHorizontal,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Logo } from "@/components/common/Brand";
import { useToast } from "@/components/common/Toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger, ToggleGroup, ToggleGroupItem } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { api, uploadFile } from "@/lib/api";
import { fmtBytes, fmtDate, fmtInt } from "@/lib/format";
import type { Numbering, RecentProject, UploadInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ZoneState {
  file?: File;
  progress?: number;
  info?: UploadInfo;
  error?: string;
}

function DropZone({
  kind,
  title,
  hint,
  accept,
  state,
  onFile,
  onClear,
}: {
  kind: "asa" | "ftd";
  title: string;
  hint: string;
  accept: string;
  state: ZoneState;
  onFile: (f: File) => void;
  onClear: () => void;
}) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const Icon = kind === "asa" ? FileCode2 : FileText;
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  };
  const uploading = state.file && !state.info && !state.error;
  const det = state.info?.detect;
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={cn(
        "relative flex min-h-[210px] flex-col rounded-card border-2 border-dashed p-5 transition-colors",
        over ? "border-accent bg-accent/5" : "border-border bg-surface-2/40",
        det?.ok && "border-solid border-ok/50 bg-ok/5",
        (det && !det.ok) || state.error ? "border-solid border-critical/50 bg-critical/5" : "",
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted" aria-hidden />
        <span className="text-[13px] font-semibold uppercase tracking-wide text-muted">{title}</span>
      </div>
      {!state.file ? (
        <button
          type="button"
          onClick={() => input.current?.click()}
          className="flex flex-1 flex-col items-center justify-center gap-2 rounded-input text-center outline-none"
        >
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <UploadCloud className="h-6 w-6" aria-hidden />
          </span>
          <span className="font-medium">Drop file here or <span className="text-primary underline-offset-2 hover:underline">browse</span></span>
          <span className="text-[12.5px] text-muted">{hint}</span>
        </button>
      ) : (
        <div className="flex flex-1 flex-col justify-center gap-3">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate font-mono text-[13px] font-medium" title={state.file.name}>{state.file.name}</p>
              <p className="text-[12px] text-muted">{fmtBytes(state.file.size)}</p>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={onClear} aria-label={`Remove ${state.file.name}`}>
              <X />
            </Button>
          </div>
          {uploading && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 text-[12.5px] text-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> {state.progress && state.progress < 100 ? `Uploading ${state.progress}%` : "Checking file type…"}
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-border">
                <div className="h-full bg-primary transition-[width]" style={{ width: `${state.progress ?? 0}%` }} />
              </div>
            </div>
          )}
          {det?.ok && (
            <p className="flex items-center gap-2 text-[13px] font-medium text-ok">
              <CheckCircle2 className="h-4 w-4" aria-hidden /> {det.label}
            </p>
          )}
          {det && !det.ok && (
            <p className="flex items-start gap-2 text-[13px] font-medium text-critical">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {det.error}
            </p>
          )}
          {state.error && (
            <p className="flex items-start gap-2 text-[13px] font-medium text-critical">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {state.error}
            </p>
          )}
        </div>
      )}
      <input
        ref={input}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export default function WelcomePage() {
  const nav = useNavigate();
  const toast = useToast();
  const [asa, setAsa] = useState<ZoneState>({});
  const [ftd, setFtd] = useState<ZoneState>({});
  const [numbering, setNumbering] = useState<Numbering>("auto");
  const [includeDisabled, setIncludeDisabled] = useState(true);
  const [ignoreComments, setIgnoreComments] = useState(true);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [recent, setRecent] = useState<RecentProject[] | null>(null);
  const [starting, setStarting] = useState(false);
  const projInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.recent().then(setRecent).catch(() => setRecent([]));
    api
      .settings()
      .then((s) => {
        setNumbering(s.numbering_default);
        setIncludeDisabled(s.include_disabled);
        setIgnoreComments(s.ignore_comments);
      })
      .catch(() => undefined);
  }, []);

  const handle = (kind: "asa" | "ftd", set: (s: ZoneState) => void, prev: ZoneState) => (file: File) => {
    if (prev.info) api.deleteUpload(prev.info.id).catch(() => undefined);
    set({ file, progress: 0 });
    uploadFile(kind, file, (p) => set({ file, progress: p }))
      .then((info) => set({ file, info, progress: 100 }))
      .catch((e: Error) => set({ file, error: e.message }));
  };
  const clear = (s: ZoneState, set: (s: ZoneState) => void) => () => {
    if (s.info) api.deleteUpload(s.info.id).catch(() => undefined);
    set({});
  };

  const ready = !!asa.info?.detect.ok && !!ftd.info?.detect.ok;

  const compare = async () => {
    if (!asa.info || !ftd.info) return;
    setStarting(true);
    try {
      const job = await api.startJob({
        asa_upload: asa.info.id,
        ftd_upload: ftd.info.id,
        numbering,
        include_disabled: includeDisabled,
        ignore_comments: ignoreComments,
      });
      nav(`/processing/${job.id}`);
    } catch (e) {
      toast({ title: "Could not start the comparison", description: (e as Error).message, tone: "critical" });
      setStarting(false);
    }
  };

  const openRecent = async (p: RecentProject) => {
    try {
      const r = await api.openProject(p.path);
      nav(`/s/${r.session_id}/dashboard`);
    } catch (e) {
      toast({ title: "Could not open project", description: (e as Error).message, tone: "critical" });
    }
  };
  const openFile = async (f: File) => {
    try {
      const r = await api.uploadProject(f);
      nav(`/s/${r.session_id}/dashboard`);
    } catch (e) {
      toast({ title: "Could not open project", description: (e as Error).message, tone: "critical" });
    }
  };

  return (
    <div className="mx-auto flex max-w-[1040px] flex-col gap-6 px-6 py-10">
      <section className="card p-8">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo size={48} />
          <p className="text-lg font-medium text-text/90">See every rule. Miss nothing.</p>
          <p className="max-w-xl text-sm text-muted">
            Compare the old Cisco ASA running config with the migrated FTD Access Control Policy. Every object is expanded to real
            IPs and ports, every rule is matched to its origin, and every difference is highlighted.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-5">
          <DropZone kind="asa" title="ASA config (before)" hint=".cfg or .txt — output of show running-config" accept=".cfg,.txt,.conf,.log,text/plain"
            state={asa} onFile={handle("asa", setAsa, asa)} onClear={clear(asa, setAsa)} />
          <DropZone kind="ftd" title="FTD policy report (after)" hint=".pdf — FMC Access Control Policy report (or FMC REST API .json export)" accept=".pdf,application/pdf,.json,application/json"
            state={ftd} onFile={handle("ftd", setFtd, ftd)} onClear={clear(ftd, setFtd)} />
        </div>

        <Collapsible open={optionsOpen} onOpenChange={setOptionsOpen} className="mt-5">
          <CollapsibleTrigger asChild>
            <button className="flex items-center gap-2 rounded-md px-1 text-[13px] font-medium text-muted hover:text-text">
              <SlidersHorizontal className="h-4 w-4" /> Options
              <ChevronDown className={cn("h-4 w-4 transition-transform", optionsOpen && "rotate-180")} />
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-3 grid grid-cols-3 gap-5 rounded-card border border-border bg-surface-2/40 p-4">
              <div className="space-y-2">
                <p className="text-[13px] font-medium">Numbering strategy</p>
                <ToggleGroup type="single" value={numbering} onValueChange={(v) => v && setNumbering(v as Numbering)} aria-label="Numbering strategy">
                  <ToggleGroupItem value="auto">Auto</ToggleGroupItem>
                  <ToggleGroupItem value="ace_only">ACE-only</ToggleGroupItem>
                  <ToggleGroupItem value="all_lines">All lines</ToggleGroupItem>
                </ToggleGroup>
                <p className="text-[12px] text-muted">How FTD rule names (ACL_#N) map to ASA lines. Auto verifies both per ACL.</p>
              </div>
              <label className="flex items-start justify-between gap-3">
                <span className="space-y-1">
                  <span className="block text-[13px] font-medium">Include disabled rules</span>
                  <span className="block text-[12px] text-muted">Inactive ASA / disabled FTD rules are still compared — enabling them later would open access.</span>
                </span>
                <Switch checked={includeDisabled} onCheckedChange={setIncludeDisabled} aria-label="Include disabled rules" />
              </label>
              <label className="flex items-start justify-between gap-3">
                <span className="space-y-1">
                  <span className="block text-[13px] font-medium">Ignore comment differences</span>
                  <span className="block text-[12px] text-muted">Remarks vs. FMC comments are shown but do not mark a rule as changed.</span>
                </span>
                <Switch checked={ignoreComments} onCheckedChange={setIgnoreComments} aria-label="Ignore comment differences" />
              </label>
            </div>
          </CollapsibleContent>
        </Collapsible>

        <div className="mt-6 flex items-center justify-between gap-4">
          <p className="flex items-center gap-2 text-[12.5px] text-muted">
            <Lock className="h-3.5 w-3.5" aria-hidden /> 100% offline — files never leave this computer. Secrets in the config are ignored.
          </p>
          <Button size="lg" onClick={compare} disabled={!ready || starting} className="min-w-44">
            {starting ? <Loader2 className="animate-spin" /> : null} Compare
          </Button>
        </div>
      </section>

      <section className="card">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="font-semibold">Recent projects</h2>
          <Button variant="secondary" size="sm" onClick={() => projInput.current?.click()}>
            <FolderOpen /> Open project…
          </Button>
          <input ref={projInput} type="file" accept=".sibit" className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) openFile(f);
              e.target.value = "";
            }} />
        </div>
        {recent === null ? (
          <div className="space-y-2 p-4">
            <div className="skeleton h-10" />
            <div className="skeleton h-10" />
          </div>
        ) : recent.length === 0 ? (
          <p className="px-5 py-6 text-sm text-muted">No saved projects yet. After a comparison, use <b>Save project</b> to keep it as a .sibit file.</p>
        ) : (
          <ul className="divide-y divide-border">
            {recent.map((p) => (
              <li key={p.path}>
                <button onClick={() => openRecent(p)} className="flex w-full items-center gap-4 px-5 py-3 text-left hover:bg-surface-2/60">
                  <FolderOpen className="h-4 w-4 shrink-0 text-muted" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{p.name}</p>
                    <p className="truncate font-mono text-[12px] text-muted">{p.asa_name} → {p.ftd_name}</p>
                  </div>
                  <span className="text-[12px] text-muted">{fmtInt(p.total)} rules</span>
                  {p.critical > 0 ? <Badge tone="critical">{p.critical} critical</Badge> : <Badge tone="ok">No critical</Badge>}
                  <span className="w-36 text-right text-[12px] text-muted">{fmtDate(p.saved)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
