import { cn } from "@/lib/utils";
import { MARK_ACCENT, MARK_ACCENT_SMALL, MARK_PATHS, MARK_PATHS_SMALL, SHIELD_PATH } from "./brand-geometry";

/** The Sibit mark, coloured by the current theme tokens. */
export function Mark({ size = 28, className, simple }: { size?: number; className?: string; simple?: boolean }) {
  const paths = simple || size <= 20 ? MARK_PATHS_SMALL : MARK_PATHS;
  const a = simple || size <= 20 ? MARK_ACCENT_SMALL : MARK_ACCENT;
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={cn("shrink-0", className)} aria-hidden="true">
      <path d={paths.join(" ")} fill="rgb(var(--primary))" />
      <rect x={a.x} y={a.y} width={a.width} height={a.height} rx={a.rx} fill="rgb(var(--accent))" />
    </svg>
  );
}

export function Logo({ size = 28, className, showText = true }: { size?: number; className?: string; showText?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <Mark size={size} />
      {showText && (
        <span className="font-semibold tracking-[-0.02em] text-text" style={{ fontSize: size * 0.72, lineHeight: 1 }}>
          Sibit
        </span>
      )}
    </span>
  );
}

/** Small illustration for empty states, built from the mark: an outline shield with blank rule lines. */
export function EmptyIllustration({ className, tone = "muted" }: { className?: string; tone?: "muted" | "ok" }) {
  const stroke = tone === "ok" ? "rgb(var(--ok))" : "rgb(var(--muted))";
  return (
    <svg viewBox="0 0 96 80" className={cn("h-20 w-24", className)} aria-hidden="true">
      <g transform="translate(16 8)">
        <path d={SHIELD_PATH} fill="rgb(var(--surface-2))" stroke={stroke} strokeOpacity="0.45" strokeWidth="1.5" strokeDasharray="3 3" />
        {[14, 23, 32, 41].map((y, i) => (
          <rect key={y} x={i === 2 ? 22 : 18} y={y} width={i === 2 ? 22 : 26} height="4" rx="2"
            fill={i === 2 ? "rgb(var(--accent))" : stroke} opacity={i === 2 ? 0.8 : 0.35} />
        ))}
      </g>
      <circle cx="78" cy="58" r="10" fill="rgb(var(--surface))" stroke={stroke} strokeOpacity="0.5" strokeWidth="1.5" />
      <path d="M85 65 L91 71" stroke={stroke} strokeOpacity="0.5" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}
