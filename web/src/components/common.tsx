"use client";

import { cn } from "@/lib/utils";
import { SEVERITIES, type Severity, type SeverityCounts } from "@/lib/api";

export const SEVERITY_STYLE: Record<Severity, string> = {
  CRITICAL: "bg-red-600 text-white",
  HIGH: "bg-orange-500 text-white",
  MEDIUM: "bg-yellow-400 text-yellow-950",
  LOW: "bg-sky-500 text-white",
  UNKNOWN: "bg-muted text-muted-foreground",
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-16 justify-center rounded px-1.5 py-0.5 text-[11px] font-semibold tracking-wide",
        SEVERITY_STYLE[severity],
        className,
      )}
    >
      {severity}
    </span>
  );
}

export function SeverityCountsInline({ counts }: { counts: SeverityCounts }) {
  const shown = SEVERITIES.filter((s) => counts[s] > 0);
  if (shown.length === 0) return <span className="text-xs text-muted-foreground">なし</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((s) => (
        <span key={s} className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", SEVERITY_STYLE[s])}>
          {s[0]} {counts[s]}
        </span>
      ))}
    </span>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-8 rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30",
        className,
      )}
      {...props}
    />
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

export function ErrorText({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return <p className="text-sm text-destructive">{children}</p>;
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  return new Date(value).toLocaleString("ja-JP", { dateStyle: "short", timeStyle: "short" });
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: React.ReactNode }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b">
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={cn(
            "-mb-px border-b-2 border-transparent px-3 py-2 text-sm whitespace-nowrap text-muted-foreground hover:text-foreground",
            value === t.value && "border-primary font-medium text-foreground",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
