"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import { todayISO, type EstimateStatus, type ProjectStatus } from "@/lib/api";

const STATUS_STYLE: Record<ProjectStatus, string> = {
  inquiry: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  proposal: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  negotiation: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
  won: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  development: "bg-blue-600/15 text-blue-700 dark:text-blue-300",
  maintenance: "bg-teal-500/15 text-teal-700 dark:text-teal-300",
  on_hold: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  lost: "bg-muted text-muted-foreground",
};

export function ProjectStatusBadge({ status }: { status: ProjectStatus | null }) {
  const t = useTranslations("labels.projectStatus");
  if (!status) return null;
  return (
    <span className={cn("inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap", STATUS_STYLE[status])}>
      {t(status)}
    </span>
  );
}

const ESTIMATE_STYLE: Record<EstimateStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  submitted: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
  won: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  lost: "bg-red-500/10 text-red-700 dark:text-red-300",
};

export function EstimateStatusBadge({ status }: { status: EstimateStatus }) {
  const t = useTranslations("labels.estimateStatus");
  return (
    <span className={cn("inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap", ESTIMATE_STYLE[status])}>
      {t(status)}
    </span>
  );
}

/** "11/9" (red and labelled when past). */
export function NextAction({ text, on }: { text: string | null; on: string | null }) {
  const t = useTranslations("deals");
  if (!text && !on) return <span className="text-muted-foreground">—</span>;
  const overdue = !!on && on < todayISO();
  return (
    <span className={cn("text-xs", overdue && "text-destructive")}>
      {text}
      {on && (
        <span className={cn("ml-1 tabular-nums", !overdue && "text-muted-foreground")}>
          {shortDate(on)}
          {overdue && ` ${t("overdue")}`}
        </span>
      )}
    </span>
  );
}

/** "2026-11-09" -> "11/9" this year, "2027/1/31" otherwise. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return y === new Date().getFullYear() ? `${m}/${d}` : `${y}/${m}/${d}`;
}

export function userLabel(u: { display_name: string | null; email: string } | null | undefined): string {
  return u ? u.display_name || u.email : "—";
}
