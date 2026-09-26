import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-px text-[12px] font-medium leading-5 [&_svg]:size-3.5 [&_svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "border-border bg-surface-2 text-muted",
        ok: "border-ok/30 bg-ok/10 text-ok",
        critical: "border-critical/35 bg-critical/10 text-critical",
        high: "border-high/35 bg-high/10 text-high",
        medium: "border-medium/35 bg-medium/10 text-medium",
        low: "border-low/35 bg-low/10 text-low",
        primary: "border-primary/35 bg-primary/10 text-primary",
        accent: "border-accent/35 bg-accent/10 text-accent",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
