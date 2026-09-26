import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  FileDown,
  FileText,
  LayoutDashboard,
  ListOrdered,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Rows3,
  Save,
  Settings,
  Shapes,
  Sun,
} from "lucide-react";
import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { Logo, Mark } from "@/components/common/Brand";
import { PageSkeleton } from "@/components/common/States";
import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import { rememberLastSession, useOptionalSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/common/Toast";

function lastSid(): string | null {
  try {
    return localStorage.getItem("sibit.lastSession");
  } catch {
    return null;
  }
}

const NAV = [
  { to: "dashboard", label: "Dashboard", icon: LayoutDashboard, session: true },
  { to: "rules", label: "Rules", icon: Rows3, session: true },
  { to: "objects", label: "Objects", icon: Shapes, session: true },
  { to: "order", label: "Order Check", icon: ListOrdered, session: true },
  { to: "reports", label: "Reports", icon: FileDown, session: true },
  { to: "/hits", label: "Hit Counts", icon: Activity, session: false },
  { to: "/settings", label: "Settings", icon: Settings, session: false },
] as const;

function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { sid: routeSid } = useParams();
  const sid = routeSid ?? lastSid();
  const loc = useLocation();
  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200",
        collapsed ? "w-[60px]" : "w-[228px]",
      )}
    >
      <div className={cn("flex h-14 items-center border-b border-border", collapsed ? "justify-center" : "px-4")}>
        <NavLink to={sid ? `/s/${sid}/dashboard` : "/"} aria-label="Sibit home" className="rounded-md">
          {collapsed ? <Mark size={26} /> : <Logo size={26} />}
        </NavLink>
      </div>
      <nav className="flex-1 space-y-0.5 p-2" aria-label="Main">
        {NAV.map((item) => {
          const disabled = item.session && !sid;
          const to = item.session ? `/s/${sid}/${item.to}` : item.to;
          const Icon = item.icon;
          const active = item.session ? loc.pathname.startsWith(`/s/${sid}/${item.to}`) : loc.pathname.startsWith(item.to);
          const content = (
            <span
              className={cn(
                "flex h-9 items-center gap-3 rounded-input px-2.5 text-[13.5px] font-medium transition-colors",
                collapsed && "justify-center px-0",
                active ? "bg-primary/10 text-text" : "text-muted hover:bg-surface-2 hover:text-text",
                disabled && "pointer-events-none opacity-40",
              )}
            >
              <Icon className={cn("h-[18px] w-[18px] shrink-0", active && "text-primary")} aria-hidden />
              {!collapsed && <span className="truncate">{item.label}</span>}
              {active && !collapsed && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />}
            </span>
          );
          const link = disabled ? (
            <span aria-disabled="true" key={item.label}>
              {content}
            </span>
          ) : (
            <NavLink key={item.label} to={to} aria-current={active ? "page" : undefined} className="block rounded-input">
              {content}
            </NavLink>
          );
          return (
            <Tip key={item.label} content={collapsed ? item.label : disabled ? "Run a comparison first" : null} side="right">
              {link}
            </Tip>
          );
        })}
      </nav>
      <div className={cn("border-t border-border p-2", collapsed && "flex justify-center")}>
        <Button variant="ghost" size={collapsed ? "icon" : "sm"} onClick={onToggle} className="w-full justify-start gap-2"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeftOpen /> : <><PanelLeftClose /> <span>Collapse</span></>}
        </Button>
      </div>
    </aside>
  );
}

function ProjectName() {
  const s = useOptionalSession();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (editing) ref.current?.select();
  }, [editing]);
  if (!s?.meta) return <span className="text-sm text-muted">No comparison loaded</span>;
  const commit = () => {
    setEditing(false);
    const name = value.trim();
    if (name && name !== s.meta?.name) {
      s.setName(name);
      api.rename(s.sid, name).catch(() => undefined);
    }
  };
  return editing ? (
    <input
      ref={ref}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setEditing(false);
      }}
      className="h-7 w-72 rounded-md border border-accent bg-surface px-2 text-[15px] font-semibold outline-none"
      aria-label="Project name"
    />
  ) : (
    <button
      className="truncate rounded-md px-1 text-left text-[15px] font-semibold hover:bg-surface-2"
      onClick={() => {
        setValue(s.meta!.name);
        setEditing(true);
      }}
      title="Rename project"
    >
      {s.meta.name}
    </button>
  );
}

function TopBar() {
  const s = useOptionalSession();
  const { resolvedTheme, toggleTheme } = usePrefs();
  const nav = useNavigate();
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!s) return;
    setSaving(true);
    try {
      const r = await api.save(s.sid, s.meta?.name);
      toast({ title: "Project saved", description: r.path, tone: "ok" });
      s.reloadMeta();
    } catch (e) {
      toast({ title: "Could not save project", description: (e as Error).message, tone: "critical" });
    } finally {
      setSaving(false);
    }
  };
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-surface/80 px-5 backdrop-blur">
      <div className="flex min-w-0 flex-1 items-center gap-4">
        <ProjectName />
        {s?.meta && (
          <div className="hidden min-w-0 items-center gap-2 text-[12.5px] text-muted lg:flex">
            <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="truncate font-mono" title="ASA config (before)">{s.meta.asa_name}</span>
            <ArrowRight className="h-3.5 w-3.5 shrink-0 text-accent" aria-label="compared with" />
            <span className="truncate font-mono" title="FTD policy report (after)">{s.meta.ftd_name}</span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        {s?.meta && (
          <Button variant="secondary" size="sm" onClick={save} disabled={saving}>
            <Save /> {s.meta.saved_path ? "Save" : "Save project"}
          </Button>
        )}
        <Tip content={resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
            {resolvedTheme === "dark" ? <Sun /> : <Moon />}
          </Button>
        </Tip>
        <Button size="sm" onClick={() => nav("/")}>
          <Plus /> New comparison
        </Button>
      </div>
    </header>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("sibit.sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  const { sid } = useParams();
  const loc = useLocation();
  useEffect(() => {
    if (sid) rememberLastSession(sid);
  }, [sid]);
  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem("sibit.sidebar", c ? "open" : "collapsed");
      } catch {
        /* ignore */
      }
      return !c;
    });
  return (
    <div className="flex h-screen min-w-[1280px] overflow-hidden">
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <motion.main
          key={loc.pathname}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="min-h-0 flex-1 overflow-auto scrollbar-thin"
        >
          <Suspense fallback={<PageSkeleton />}>{children ?? <Outlet />}</Suspense>
        </motion.main>
      </div>
    </div>
  );
}
