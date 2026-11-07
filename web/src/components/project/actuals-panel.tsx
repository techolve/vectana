"use client";

import { useTranslations } from "next-intl";

import { HOURS_PER_DAY, yen, type Actuals, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, ErrorText } from "@/components/common";
import { userLabel } from "@/components/sales/status";

const days = (n: number) => (Math.round(n * 10) / 10).toString();

/** Bar of actual against estimate; amber past 90%, red past 100%. */
function Bar({ actual, estimate }: { actual: number; estimate: number | null }) {
  if (!estimate) return <div className="h-1.5 w-full rounded-full bg-muted" />;
  const ratio = actual / estimate;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className={cn("h-full rounded-full", ratio > 1 ? "bg-red-600" : ratio > 0.9 ? "bg-amber-500" : "bg-primary")}
        style={{ width: `${Math.min(ratio, 1) * 100}%` }}
      />
    </div>
  );
}

/** 見積と実績: won estimates' effort against the hours people entered. */
export function ActualsPanel({ project }: { project: Project }) {
  const t = useTranslations("actuals");
  const { data, error } = useApi<Actuals>(`/projects/${project.id}/actuals`);
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data) return null;
  const ratio = data.estimate_days ? data.actual_days / data.estimate_days : null;
  const maxPerson = Math.max(1, ...data.people.map((p) => p.actual_days));

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t("description", { hours: HOURS_PER_DAY })}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>{t("effort")}</CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {t("days", { days: days(data.actual_days) })}
              <span className="ml-1 text-sm font-normal text-muted-foreground">
                / {data.estimate_days != null ? t("days", { days: days(data.estimate_days) }) : "—"}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1.5">
            <Bar actual={data.actual_days} estimate={data.estimate_days} />
            <span className={cn("text-xs text-muted-foreground", ratio != null && ratio > 1 && "text-destructive")}>
              {ratio != null ? t("consumed", { percent: Math.round(ratio * 100) }) : t("noEstimate")}
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>{t("thisMonth")}</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{t("days", { days: days(data.this_month_days) })}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">{t("hoursTotal", { hours: days(data.actual_hours) })}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>{t("amount")}</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{yen(data.estimate_amount)}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">{t("amountHint")}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>{t("cost")}</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{data.actual_cost != null ? yen(data.actual_cost) : "—"}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {data.actual_cost == null
              ? t("costHidden")
              : data.estimate_amount
                ? t("margin", { percent: Math.round(((data.estimate_amount - data.actual_cost) / data.estimate_amount) * 100) })
                : t("costHint")}
          </CardContent>
        </Card>
      </div>

      {data.actual_hours === 0 && data.phases.length === 0 ? (
        <Empty>{t("empty")}</Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("byPhase")}</CardTitle>
              <CardDescription>{t("byPhaseHint")}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {data.phases.map((p) => (
                <div key={p.task_id ?? "none"} className="grid gap-1">
                  <div className="flex items-baseline justify-between gap-2 text-sm">
                    <span className={cn("truncate", !p.task_id && "text-muted-foreground")}>{p.title ?? t("noPhase")}</span>
                    <span className="shrink-0 text-xs tabular-nums">
                      {t("days", { days: days(p.actual_days) })}
                      <span className="text-muted-foreground">
                        {" / "}
                        {p.estimate_days != null ? t("days", { days: days(p.estimate_days) }) : "—"}
                      </span>
                    </span>
                  </div>
                  <Bar actual={p.actual_days} estimate={p.estimate_days} />
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("byPerson")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              {data.people.map((p) => (
                <div key={p.user.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 gap-y-1 text-sm">
                  <span className="truncate">{userLabel(p.user)}</span>
                  <span className="text-xs tabular-nums">{t("days", { days: days(p.actual_days) })}</span>
                  <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary/70" style={{ width: `${(p.actual_days / maxPerson) * 100}%` }} />
                  </div>
                </div>
              ))}
              {data.people.length === 0 && <p className="text-xs text-muted-foreground">{t("nobody")}</p>}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
