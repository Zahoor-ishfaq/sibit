import { Monitor, Moon, Plus, Power, Rows2, Rows4, Sun, Trash2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton, ToggleGroup, ToggleGroupItem } from "@/components/ui/misc";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { Numbering, Settings } from "@/lib/types";

function Row({ title, desc, children }: { title: string; desc?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-border px-5 py-4 last:border-b-0">
      <div className="space-y-0.5">
        <p className="text-[13.5px] font-medium">{title}</p>
        {desc && <p className="max-w-xl text-[12.5px] text-muted">{desc}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const { theme, setTheme, density, setDensity } = usePrefs();
  const toast = useToast();
  const [s, setS] = useState<Settings | null>(null);
  const [name, setName] = useState("");
  const [proto, setProto] = useState("any");
  const [port, setPort] = useState("");
  const [version, setVersion] = useState("");

  useEffect(() => {
    api.settings().then(setS).catch(() => undefined);
    api.health().then((h) => setVersion(h.version)).catch(() => undefined);
  }, []);

  const patch = async (p: Partial<Settings>) => {
    try {
      setS(await api.saveSettings(p));
    } catch (e) {
      toast({ title: "Could not save setting", description: (e as Error).message, tone: "critical" });
    }
  };

  const addOverride = () => {
    const n = name.trim().toLowerCase();
    const v = Number(port);
    if (!/^[a-z0-9][a-z0-9-]*$/.test(n) || !Number.isInteger(v) || v < 0 || v > 65535) {
      toast({ title: "Enter a port name (letters, digits, '-') and a port number 0–65535", tone: "critical" });
      return;
    }
    const key = proto === "any" ? n : `${proto}/${n}`;
    patch({ port_overrides: { ...(s?.port_overrides ?? {}), [key]: v } });
    setName("");
    setPort("");
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-lg font-semibold">Settings</h1>

      <section className="card">
        <h2 className="border-b border-border px-5 py-3 text-[13px] font-semibold uppercase tracking-wide text-muted">Appearance</h2>
        <Row title="Theme" desc="Dark is the default.">
          <ToggleGroup type="single" value={theme} onValueChange={(v) => v && setTheme(v as "dark" | "light" | "system")} aria-label="Theme">
            <ToggleGroupItem value="dark"><Moon /> Dark</ToggleGroupItem>
            <ToggleGroupItem value="light"><Sun /> Light</ToggleGroupItem>
            <ToggleGroupItem value="system"><Monitor /> System</ToggleGroupItem>
          </ToggleGroup>
        </Row>
        <Row title="Density" desc="Compact shows more rules on screen.">
          <ToggleGroup type="single" value={density} onValueChange={(v) => v && setDensity(v as "comfortable" | "compact")} aria-label="Density">
            <ToggleGroupItem value="comfortable"><Rows2 /> Comfortable</ToggleGroupItem>
            <ToggleGroupItem value="compact"><Rows4 /> Compact</ToggleGroupItem>
          </ToggleGroup>
        </Row>
      </section>

      <section className="card">
        <h2 className="border-b border-border px-5 py-3 text-[13px] font-semibold uppercase tracking-wide text-muted">Comparison defaults</h2>
        {!s ? (
          <div className="space-y-2 p-5"><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
        ) : (
          <>
            <Row title="Numbering strategy" desc="How FTD rule names (ACL_#N) map to ASA line numbers. Auto tries both on the first 50 rules of each ACL and keeps the better match.">
              <Select value={s.numbering_default} onValueChange={(v) => patch({ numbering_default: v as Numbering })}>
                <SelectTrigger className="w-52" aria-label="Numbering strategy"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto (recommended)</SelectItem>
                  <SelectItem value="ace_only">ACE-only</SelectItem>
                  <SelectItem value="all_lines">All lines</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row title="Include disabled rules" desc="Compare inactive ASA and disabled FTD rules too.">
              <Switch checked={s.include_disabled} onCheckedChange={(v) => patch({ include_disabled: v })} aria-label="Include disabled rules" />
            </Row>
            <Row title="Ignore comment differences" desc="Remark/comment text is shown but does not mark a rule as changed.">
              <Switch checked={s.ignore_comments} onCheckedChange={(v) => patch({ ignore_comments: v })} aria-label="Ignore comment differences" />
            </Row>
          </>
        )}
      </section>

      <section className="card">
        <h2 className="border-b border-border px-5 py-3 text-[13px] font-semibold uppercase tracking-wide text-muted">Port-name overrides</h2>
        <p className="px-5 pt-4 text-[12.5px] text-muted">
          Override how Cisco port names resolve to numbers (for example <span className="font-mono">tcp/kerberos = 750</span>). Applies to the next comparison.
        </p>
        <div className="flex items-end gap-2 px-5 py-4">
          <label className="space-y-1">
            <span className="text-[12px] text-muted">Protocol</span>
            <Select value={proto} onValueChange={setProto}>
              <SelectTrigger className="w-32" aria-label="Protocol"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="any">tcp + udp</SelectItem>
                <SelectItem value="tcp">tcp</SelectItem>
                <SelectItem value="udp">udp</SelectItem>
              </SelectContent>
            </Select>
          </label>
          <label className="flex-1 space-y-1">
            <span className="text-[12px] text-muted">Port name</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="kerberos" className="font-mono" />
          </label>
          <label className="w-32 space-y-1">
            <span className="text-[12px] text-muted">Port</span>
            <Input value={port} onChange={(e) => setPort(e.target.value.replace(/\D/g, ""))} placeholder="750" className="font-mono"
              onKeyDown={(e) => e.key === "Enter" && addOverride()} />
          </label>
          <Button onClick={addOverride}><Plus /> Add</Button>
        </div>
        {s && Object.keys(s.port_overrides).length > 0 && (
          <ul className="divide-y divide-border border-t border-border">
            {Object.entries(s.port_overrides).map(([k, v]) => (
              <li key={k} className="flex items-center gap-3 px-5 py-2">
                <span className="flex-1 font-mono text-[13px]">{k}</span>
                <span className="font-mono text-[13px]">{v}</span>
                <Button variant="ghost" size="icon-sm" aria-label={`Remove ${k}`}
                  onClick={() => {
                    const next = { ...s.port_overrides };
                    delete next[k];
                    patch({ port_overrides: next });
                  }}>
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <Row title="Quit Sibit" desc={`Stops the local server. Unsaved comparisons are discarded. ${version ? `Version ${version}.` : ""}`}>
          <Button variant="secondary" onClick={() => api.shutdown().then(() => toast({ title: "Sibit has stopped. You can close this tab." })).catch(() => undefined)}>
            <Power /> Quit
          </Button>
        </Row>
      </section>
    </div>
  );
}
