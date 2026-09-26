import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "./api";
import type { Filters, Meta, Row } from "./types";

/** Loaded comparison: meta + all rows, cached per session id for the app's lifetime. */
interface SessionState {
  sid: string;
  meta: Meta | null;
  rows: Row[] | null;
  error: string | null;
  reloadMeta: () => void;
  setName: (name: string) => void;
  /** Last filters used on the Rules screen — Reports can export exactly this view. */
  lastFilters: Filters | null;
  lastFilteredCount: number | null;
  setLastFilters: (f: Filters, count: number) => void;
}

const cache = new Map<string, { meta?: Meta; rows?: Row[] }>();
const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { sid = "" } = useParams();
  const c = cache.get(sid) ?? {};
  const [meta, setMeta] = useState<Meta | null>(c.meta ?? null);
  const [rows, setRows] = useState<Row[] | null>(c.rows ?? null);
  const [error, setError] = useState<string | null>(null);
  const [lastFilters, setLF] = useState<Filters | null>(null);
  const [lastFilteredCount, setLFC] = useState<number | null>(null);
  const current = useRef(sid);

  const load = useCallback(
    (force = false) => {
      current.current = sid;
      const cached = cache.get(sid) ?? {};
      if (!force && cached.meta && cached.rows) {
        setMeta(cached.meta);
        setRows(cached.rows);
        return;
      }
      setError(null);
      Promise.all([api.meta(sid), cached.rows && !force ? Promise.resolve(cached.rows) : api.rows(sid)])
        .then(([m, r]) => {
          cache.set(sid, { meta: m, rows: r });
          if (current.current !== sid) return;
          setMeta(m);
          setRows(r);
        })
        .catch((e: ApiError) => current.current === sid && setError(e.message));
    },
    [sid],
  );

  useEffect(() => {
    setLF(null);
    setLFC(null);
    load();
  }, [load]);

  const setName = useCallback(
    (name: string) => {
      setMeta((m) => {
        if (!m) return m;
        const next = { ...m, name };
        const cc = cache.get(sid);
        if (cc) cc.meta = next;
        return next;
      });
    },
    [sid],
  );

  const value = useMemo<SessionState>(
    () => ({
      sid,
      meta,
      rows,
      error,
      reloadMeta: () => load(true),
      setName,
      lastFilters,
      lastFilteredCount,
      setLastFilters: (f, n) => {
        setLF(f);
        setLFC(n);
      },
    }),
    [sid, meta, rows, error, load, setName, lastFilters, lastFilteredCount],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}

export function useOptionalSession(): SessionState | null {
  return useContext(SessionContext);
}

export function rememberLastSession(sid: string) {
  try {
    localStorage.setItem("sibit.lastSession", sid);
  } catch {
    /* ignore */
  }
}
