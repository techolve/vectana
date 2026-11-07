"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { AlarmClockIcon, BugIcon, CalendarClockIcon, ChevronDownIcon, ChevronRightIcon, DownloadIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { apiDownload, type OrgDashboard, type OrgRow } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Empty,
  ErrorText,
  OptionSelect,
  PageHeader,
  PageTabs,
  SEVERITY_STYLE,
  SeverityBadge,
  SeverityCountsInline,
} from "@/components/common";
import { EOL_STYLE } from "@/components/eol-table";

function rowKey(row: OrgRow): string {
  return row.kind === "unassigned" ? `none:${row.company_id}` : `${row.kind}:${row.id}`;
}

/** Each row's ancestor keys, from the depth-first order the API returns. */
function ancestors(rows: OrgRow[]): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const stack: string[] = [];
  for (const row of rows) {
    stack.length = row.depth;
    out.set(rowKey(row), [...stack]);
    stack[row.depth] = rowKey(row);
  }
  return out;
}

export default function OrgDashboardPage() {
  const t = useTranslations("org");
  const { data, error } = useApi<OrgDashboard>("/org-dashboard");
  const [companyId, setCompanyId] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<"overdue" | "eol">("overdue");

  const companies = useMemo(() => (data?.rows ?? []).filter((r) => r.kind === "company"), [data]);
  const parents = useMemo(() => ancestors(data?.rows ?? []), [data]);

  if (!data) return <ErrorText>{error}</ErrorText>;

  const selected = companyId ? companies.find((c) => c.id === companyId) : undefined;
  const totals = selected ?? data.totals;
  const rows = data.rows.filter(
    (r) =>
      (!companyId || r.company_id === companyId) &&
      !(parents.get(rowKey(r)) ?? []).some((key) => collapsed.has(key)),
  );
  const overdue = data.overdue.filter((i) => !companyId || i.company_id === companyId);
  const upcomingEol = data.upcoming_eol.filter((e) => !companyId || e.company_id === companyId);
  const hasChildren = (row: OrgRow) => data.rows.some((r) => (parents.get(rowKey(r)) ?? []).at(-1) === rowKey(row));

  function toggle(row: OrgRow) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      const key = rowKey(row);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function download() {
    try {
      const q = companyId ? `?company_id=${companyId}` : "";
      await apiDownload(`/org-dashboard.csv${q}`, `vectana-org-${data!.today}.csv`);
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <>
            {companies.length > 1 && (
              <OptionSelect
                value={companyId}
                onValueChange={setCompanyId}
                options={[{ value: "", label: t("allCompanies") }, ...companies.map((c) => ({ value: c.id!, label: c.name }))]}
              />
            )}
            <Button variant="outline" onClick={download} disabled={data.rows.length === 0}>
              <DownloadIcon />
              {t("csv")}
            </Button>
          </>
        }
      />
      <ErrorText>{error}</ErrorText>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Stat icon={AlarmClockIcon} label={t("overdue")} value={totals.overdue} accent={totals.overdue ? SEVERITY_STYLE.CRITICAL : undefined} />
        <Stat icon={BugIcon} label="CRITICAL" value={totals.open_counts.CRITICAL} accent={totals.open_counts.CRITICAL ? SEVERITY_STYLE.CRITICAL : undefined} />
        <Stat icon={BugIcon} label="HIGH" value={totals.open_counts.HIGH} accent={totals.open_counts.HIGH ? SEVERITY_STYLE.HIGH : undefined} />
        <Stat icon={CalendarClockIcon} label={t("eolReached")} value={totals.eol_counts.eol} accent={totals.eol_counts.eol ? EOL_STYLE.eol : undefined} />
        <Stat
          icon={CalendarClockIcon}
          label={t("eolApproaching")}
          value={totals.eol_counts.approaching}
          accent={totals.eol_counts.approaching ? EOL_STYLE.approaching : undefined}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("units")}</CardTitle>
          <CardDescription>
            {t("slaNote", {
              critical: data.sla_days.CRITICAL,
              high: data.sla_days.HIGH,
              medium: data.sla_days.MEDIUM,
              low: data.sla_days.LOW,
            })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <Empty>{t("empty")}</Empty>
          ) : (
            <>
              <Table className="min-w-[60rem]">
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("unit")}</TableHead>
                    <TableHead className="text-right">{t("projects")}</TableHead>
                    <TableHead>{t("open")}</TableHead>
                    <TableHead className="text-right">{t("overdue")}</TableHead>
                    <TableHead>{t("eol")}</TableHead>
                    <TableHead>{t("nearestEol")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={rowKey(row)} className={cn(row.kind === "company" && "bg-muted/40")}>
                      <TableCell>
                        <div className="flex min-w-48 items-center gap-1 whitespace-nowrap" style={{ paddingLeft: `${row.depth * 1.25}rem` }}>
                          {hasChildren(row) ? (
                            <button
                              type="button"
                              className="text-muted-foreground hover:text-foreground"
                              onClick={() => toggle(row)}
                              aria-label={collapsed.has(rowKey(row)) ? t("expand") : t("collapse")}
                            >
                              {collapsed.has(rowKey(row)) ? <ChevronRightIcon className="size-4" /> : <ChevronDownIcon className="size-4" />}
                            </button>
                          ) : (
                            <span className="inline-block size-4" />
                          )}
                          <span className={cn(row.kind === "company" && "font-medium", row.kind === "unassigned" && "text-muted-foreground")}>
                            {row.kind === "unassigned" ? t("unassigned") : row.name}
                          </span>
                          {!row.complete && (
                            <span className="ml-1 text-xs text-muted-foreground" title={t("partialHint")}>
                              {t("partial")}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{row.project_count}</TableCell>
                      <TableCell className="min-w-44">
                        <SeverityCountsInline counts={row.open_counts} empty={t("none")} />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {row.overdue > 0 ? (
                          <span className="font-semibold text-red-600 dark:text-red-400" title={t("oldestOverdue", { days: row.oldest_overdue_days ?? 0 })}>
                            {row.overdue}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </TableCell>
                      <TableCell className="min-w-52">
                        <EolCountsInline eol={row.eol_counts.eol} approaching={row.eol_counts.approaching} />
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        <DaysLeft days={row.nearest_eol_days} date={row.nearest_eol_date} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {rows.some((r) => !r.complete) && <p className="mt-3 text-xs text-muted-foreground">{t("partialHint")}</p>}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <PageTabs
            value={tab}
            onChange={setTab}
            tabs={[
              { value: "overdue", label: t("overdueTab", { count: overdue.length }) },
              { value: "eol", label: t("eolTab", { count: upcomingEol.length }) },
            ]}
          />
          {tab === "overdue" &&
            (overdue.length === 0 ? (
              <Empty>{t("noOverdue")}</Empty>
            ) : (
              <Table className="min-w-[44rem]">
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("severity")}</TableHead>
                    <TableHead>{t("project")}</TableHead>
                    <TableHead>{t("package")}</TableHead>
                    <TableHead>{t("vuln")}</TableHead>
                    <TableHead>{t("due")}</TableHead>
                    <TableHead className="text-right">{t("daysOver")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {overdue.map((i) => (
                    <TableRow key={i.match_id}>
                      <TableCell>
                        <SeverityBadge severity={i.severity} />
                      </TableCell>
                      <TableCell>
                        <Link href={{ pathname: "/projects/detail/", query: { id: i.project_id } }} className="hover:underline">
                          {i.project_name}
                        </Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {i.package_name}@{i.package_version}
                      </TableCell>
                      <TableCell>
                        <a href={`https://osv.dev/vulnerability/${i.vuln_id}`} target="_blank" rel="noreferrer" className="font-mono text-xs hover:underline">
                          {i.vuln_id}
                        </a>
                      </TableCell>
                      <TableCell className="text-xs tabular-nums">{i.due_date}</TableCell>
                      <TableCell className="text-right font-semibold tabular-nums text-red-600 dark:text-red-400">{i.days_overdue}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ))}
          {tab === "eol" &&
            (upcomingEol.length === 0 ? (
              <Empty>{t("noEol")}</Empty>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("project")}</TableHead>
                    <TableHead>{t("product")}</TableHead>
                    <TableHead>{t("eolDate")}</TableHead>
                    <TableHead>{t("nearestEol")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {upcomingEol.map((e) => (
                    <TableRow key={e.finding_id}>
                      <TableCell>
                        <Link href={{ pathname: "/projects/detail/", query: { id: e.project_id } }} className="hover:underline">
                          {e.project_name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        {e.product_label} {e.cycle ?? e.version}
                      </TableCell>
                      <TableCell className="text-xs tabular-nums">{e.eol_date}</TableCell>
                      <TableCell>
                        <DaysLeft days={e.days_left} date={null} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ))}
        </CardContent>
      </Card>
    </>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <Card className={cn("h-full", accent)}>
      <CardHeader>
        <CardDescription className={cn("flex items-center gap-1.5", accent && "text-current opacity-90")}>
          <Icon className="size-4 shrink-0" />
          <span className="truncate">{label}</span>
        </CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

function EolCountsInline({ eol, approaching }: { eol: number; approaching: number }) {
  const t = useTranslations();
  if (eol + approaching === 0) return <span className="text-xs text-muted-foreground">{t("common.none")}</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {eol > 0 && (
        <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", EOL_STYLE.eol)}>
          {t("eol.statusLabel.eol")} {eol}
        </span>
      )}
      {approaching > 0 && (
        <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", EOL_STYLE.approaching)}>
          {t("eol.statusLabel.approaching")} {approaching}
        </span>
      )}
    </span>
  );
}

function DaysLeft({ days, date }: { days: number | null; date: string | null }) {
  const t = useTranslations("org");
  if (days === null) return <span className="text-xs text-muted-foreground">-</span>;
  const text = days < 0 ? t("daysPassed", { days: -days }) : t("daysLeft", { days });
  return (
    <span
      className={cn(
        "text-xs tabular-nums",
        days < 0 ? "font-semibold text-red-600 dark:text-red-400" : "text-orange-600 dark:text-orange-400",
      )}
      title={date ?? undefined}
    >
      {text}
    </span>
  );
}
