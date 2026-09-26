import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";

export type Theme = "dark" | "light" | "system";
export type Density = "comfortable" | "compact";

interface Prefs {
  theme: Theme;
  resolvedTheme: "dark" | "light";
  density: Density;
  setTheme: (t: Theme) => void;
  setDensity: (d: Density) => void;
  toggleTheme: () => void;
}

const PrefsContext = createContext<Prefs | null>(null);

function read<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) || fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, v: string) {
  try {
    localStorage.setItem(key, v);
  } catch {
    /* storage unavailable */
  }
}

const systemDark = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches;

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => read<Theme>("sibit.theme", "dark"));
  const [density, setDensityState] = useState<Density>(() => read<Density>("sibit.density", "comfortable"));
  const [sysDark, setSysDark] = useState(systemDark);

  useEffect(() => {
    if (typeof matchMedia === "undefined") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setSysDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const resolvedTheme = theme === "system" ? (sysDark ? "dark" : "light") : theme;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolvedTheme === "dark");
  }, [resolvedTheme]);
  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);

  // Server settings are the source of truth; localStorage only avoids a flash on load.
  useEffect(() => {
    api
      .settings()
      .then((s) => {
        setThemeState(s.theme);
        setDensityState(s.density);
        write("sibit.theme", s.theme);
        write("sibit.density", s.density);
      })
      .catch(() => undefined);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    write("sibit.theme", t);
    api.saveSettings({ theme: t }).catch(() => undefined);
  }, []);
  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
    write("sibit.density", d);
    api.saveSettings({ density: d }).catch(() => undefined);
  }, []);
  const toggleTheme = useCallback(() => setTheme(resolvedTheme === "dark" ? "light" : "dark"), [resolvedTheme, setTheme]);

  const value = useMemo(
    () => ({ theme, resolvedTheme, density, setTheme, setDensity, toggleTheme }) as Prefs,
    [theme, resolvedTheme, density, setTheme, setDensity, toggleTheme],
  );
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): Prefs {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs outside PrefsProvider");
  return ctx;
}
