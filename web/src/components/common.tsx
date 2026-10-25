"use client";

import { useCallback } from "react";
import { useLocale } from "next-intl";

import { cn } from "@/lib/utils";
import { SEVERITIES, type Severity, type SeverityCounts } from "@/lib/api";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

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

export function SeverityCountsInline({ counts, empty }: { counts: SeverityCounts; empty: string }) {
  const shown = SEVERITIES.filter((s) => counts[s] > 0);
  if (shown.length === 0) return <span className="text-xs text-muted-foreground">{empty}</span>;
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
        {description && <div className="mt-1 text-sm text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export type Option = { value: string; label: React.ReactNode };

// Base UI's Select has no notion of an empty value, so "" maps to a sentinel.
const EMPTY = "__empty__";

/** shadcn Select with a plain value/options API (value "" = nothing chosen). */
export function OptionSelect({
  value,
  onValueChange,
  options,
  className,
  disabled,
  title,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: Option[];
  className?: string;
  disabled?: boolean;
  title?: string;
}) {
  const items = options.map((o) => ({ value: o.value === "" ? EMPTY : o.value, label: o.label }));
  return (
    <Select
      items={items}
      value={value === "" ? EMPTY : value}
      onValueChange={(v) => onValueChange(v === EMPTY || v == null ? "" : String(v))}
      disabled={disabled}
    >
      <SelectTrigger className={cn("min-w-32", className)} title={title}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
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

/** A labelled form control built from shadcn Field parts. */
export function LabeledField({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={htmlFor}>{label}</FieldLabel>
      {children}
      {hint && <FieldDescription>{hint}</FieldDescription>}
    </Field>
  );
}

export function useFormatDate() {
  const locale = useLocale();
  return useCallback(
    (value: string | null | undefined) =>
      value ? new Date(value).toLocaleString(locale, { dateStyle: "short", timeStyle: "short" }) : "-",
    [locale],
  );
}

/** Underlined page tabs (shadcn Tabs, "line" variant). Content is rendered by the caller. */
export function PageTabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: React.ReactNode }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as T)} className="mb-4">
      <TabsList variant="line" className="w-full justify-start overflow-x-auto border-b">
        {tabs.map((t) => (
          <TabsTrigger key={t.value} value={t.value} className="flex-none">
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
