"use client";

import { useState } from "react";
import { BugIcon, CalendarClockIcon, FolderIcon, PackageIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import type { Dashboard, Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Empty,
  ErrorText,
  PageHeader,
  PageTabs,
  SEVERITY_STYLE,
  SeverityCountsInline,
  useFormatDate,
} from "@/components/common";
import { MatchTable } from "@/components/match-table";
import { EOL_STYLE, EolTable } from "@/components/eol-table";
import { useMe } from "@/components/app-shell";

export default function DashboardPage() {
  const t = useTranslations();
  const me = useMe();
  const { data, error, reload } = useApi<Dashboard>("/dashboard");
  const [tab, setTab] = useState<"vulns" | "eol">("vulns");

  return (
    <>
      <PageHeader title={t("dashboard.title")} description={t("dashboard.description", { group: me.group_name })} />
      <ErrorText>{error}</ErrorText>
      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <StatCard icon={FolderIcon} label={t("dashboard.projects")} value={data.project_count} href="/projects/" />
            <StatCard icon={PackageIcon} label={t("dashboard.packages")} value={data.package_count} />
            <StatCard
              icon={BugIcon}
              label="CRITICAL"
              value={data.open_counts.CRITICAL}
              accent={data.open_counts.CRITICAL ? SEVERITY_STYLE.CRITICAL : undefined}
              href={{ pathname: "/vulnerabilities/", query: { severity: "CRITICAL" } }}
            />
            <StatCard
              icon={BugIcon}
              label="HIGH"
              value={data.open_counts.HIGH}
              accent={data.open_counts.HIGH ? SEVERITY_STYLE.HIGH : undefined}
              href={{ pathname: "/vulnerabilities/", query: { severity: "HIGH" } }}
            />
            <StatCard
              icon={CalendarClockIcon}
              label={t("dashboard.eolReached")}
              value={data.eol_counts.eol}
              accent={data.eol_counts.eol ? EOL_STYLE.eol : undefined}
              href="/eol/"
            />
            <StatCard
              icon={CalendarClockIcon}
              label={t("dashboard.eolApproaching")}
              value={data.eol_counts.approaching}
              accent={data.eol_counts.approaching ? EOL_STYLE.approaching : undefined}
              href="/eol/"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>{t("dashboard.health")}</CardTitle>
              <CardDescription>{t("dashboard.healthDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              {data.projects.length === 0 ? (
                <Empty>{t("dashboard.noProjects")}</Empty>
              ) : (
                <ProjectHealthTable projects={data.projects} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("dashboard.todo")}</CardTitle>
              <CardAction />
            </CardHeader>
            <CardContent>
              <PageTabs
                value={tab}
                onChange={setTab}
                tabs={[
                  { value: "vulns", label: t("dashboard.tabVulns", { count: data.recent.length }) },
                  { value: "eol", label: t("dashboard.tabEol", { count: data.eol.length }) },
                ]}
              />
              {tab === "vulns" &&
                (data.recent.length === 0 ? (
                  <Empty>
                    {t("dashboard.empty")}{" "}
                    {data.package_count === 0 &&
                      t.rich("dashboard.emptyHint", {
                        link: (chunks) => (
                          <Link href="/projects/" className="underline">
                            {chunks}
                          </Link>
                        ),
                      })}
                  </Empty>
                ) : (
                  <MatchTable matches={data.recent} onChanged={reload} showProject />
                ))}
              {tab === "eol" &&
                (data.eol.length === 0 ? <Empty>{t("dashboard.eolEmpty")}</Empty> : <EolTable findings={data.eol} showProject />)}
            </CardContent>
          </Card>
        </>
      )}
    </>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
  href,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  accent?: string;
  href?: React.ComponentProps<typeof Link>["href"];
}) {
  const card = (
    <Card className={cn("h-full transition-colors", href && "hover:bg-muted/50", accent)}>
      <CardHeader>
        <CardDescription className={cn("flex items-center gap-1.5", accent && "text-current opacity-90")}>
          <Icon className="size-4" />
          {label}
        </CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
  return href ? <Link href={href}>{card}</Link> : card;
}

function ProjectHealthTable({ projects }: { projects: Project[] }) {
  const t = useTranslations();
  const formatDate = useFormatDate();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("dashboard.project")}</TableHead>
          <TableHead>{t("dashboard.vulns")}</TableHead>
          <TableHead>{t("dashboard.eol")}</TableHead>
          <TableHead className="text-right">{t("dashboard.packages")}</TableHead>
          <TableHead>{t("dashboard.lastScanned")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {projects.map((p) => (
          <TableRow key={p.id}>
            <TableCell>
              <Link href={{ pathname: "/projects/detail/", query: { id: p.id } }} className="font-medium hover:underline">
                {p.name}
              </Link>
            </TableCell>
            <TableCell>
              <SeverityCountsInline counts={p.open_counts} empty={t("common.none")} />
            </TableCell>
            <TableCell>
              {p.eol_counts.eol + p.eol_counts.approaching === 0 ? (
                <span className="text-xs text-muted-foreground">{t("common.none")}</span>
              ) : (
                <span className="flex flex-wrap gap-1">
                  {p.eol_counts.eol > 0 && (
                    <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", EOL_STYLE.eol)}>
                      {t("eol.statusLabel.eol")} {p.eol_counts.eol}
                    </span>
                  )}
                  {p.eol_counts.approaching > 0 && (
                    <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", EOL_STYLE.approaching)}>
                      {t("eol.statusLabel.approaching")} {p.eol_counts.approaching}
                    </span>
                  )}
                </span>
              )}
            </TableCell>
            <TableCell className="text-right tabular-nums">{p.package_count}</TableCell>
            <TableCell className="text-xs">{formatDate(p.last_scanned_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
