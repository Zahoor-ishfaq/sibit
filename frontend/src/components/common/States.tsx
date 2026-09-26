import { AlertTriangle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { EmptyIllustration } from "./Brand";

export function EmptyState({
  title,
  children,
  action,
  className,
  tone,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
  tone?: "muted" | "ok";
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 px-6 py-12 text-center", className)}>
      <EmptyIllustration tone={tone} />
      <div className="space-y-1">
        <p className="font-semibold">{title}</p>
        {children && <div className="mx-auto max-w-md text-sm text-muted">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry, className }: { message: string; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" className={cn("card mx-auto flex max-w-xl items-start gap-3 border-critical/40 p-4", className)}>
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-critical" />
      <div className="flex-1 space-y-2">
        <p className="font-semibold">Something went wrong</p>
        <p className="text-sm text-muted">{message}</p>
        {onRetry && (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            <RefreshCw /> Try again
          </Button>
        )}
      </div>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-5 p-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-6 w-60" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 12 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-label="Loading rules">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8" style={{ opacity: 1 - i * 0.06 }} />
      ))}
    </div>
  );
}
