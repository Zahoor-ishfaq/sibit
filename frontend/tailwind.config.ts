import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// Tokens from the spec (9.3), defined as CSS variables in src/styles/globals.css.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: token("surface"),
        "surface-2": token("surface-2"),
        border: token("border"),
        text: token("text"),
        muted: token("muted"),
        primary: { DEFAULT: token("primary"), fg: token("primary-fg") },
        accent: token("accent"),
        critical: token("critical"),
        high: token("high"),
        medium: token("medium"),
        low: token("low"),
        ok: token("ok"),
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontSize: { base: ["14px", "20px"] },
      borderRadius: { card: "12px", input: "8px" },
      boxShadow: {
        soft: "0 1px 2px rgb(15 23 42 / 0.04), 0 4px 16px -4px rgb(15 23 42 / 0.08)",
        pop: "0 8px 30px -6px rgb(2 6 23 / 0.35)",
      },
      keyframes: {
        "slide-in-right": { from: { transform: "translateX(24px)", opacity: "0" }, to: { transform: "none", opacity: "1" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "slide-in-right": "slide-in-right 180ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        "fade-in": "fade-in 150ms ease-out",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
