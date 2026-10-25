"use client";

import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { SEVERITIES, type Dashboard } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, ErrorText, PageHeader, SEVERITY_STYLE } from "@/components/common";
import { MatchTable } from "@/components/match-table";
import { useMe } from "@/components/app-shell";

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const me = useMe();
  const { data, error, reload } = useApi<Dashboard>("/dashboard");

  return (
    <>
      <PageHeader title={t("title")} description={t("description", { group: me.group_name })} />
      <ErrorText>{error}</ErrorText>
      {data && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
            <Stat label={t("projects")} value={data.project_count} />
            <Stat label={t("packages")} value={data.package_count} />
            {SEVERITIES.map((s) => (
              <Link key={s} href={{ pathname: "/vulnerabilities/", query: { severity: s } }}>
                <Stat label={s} value={data.open_counts[s]} className={data.open_counts[s] ? SEVERITY_STYLE[s] : ""} />
              </Link>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle>{t("recent")}</CardTitle>
            </CardHeader>
            <CardContent>
              {data.recent.length === 0 ? (
                <Empty>
                  {t("empty")}{" "}
                  {data.package_count === 0 &&
                    t.rich("emptyHint", {
                      link: (chunks) => (
                        <Link href="/projects/" className="underline">
                          {chunks}
                        </Link>
                      ),
                    })}
                </Empty>
              ) : (
                <MatchTable matches={data.recent} onChanged={reload} showProject />
              )}
            </CardContent>
          </Card>
        </>
      )}
    </>
  );
}

function Stat({ label, value, className }: { label: string; value: number; className?: string }) {
  return (
    <div className={cn("rounded-xl border p-3", className)}>
      <div className="text-xs opacity-80">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}
