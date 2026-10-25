"use client";

import Link from "next/link";

import { SEVERITIES, type Dashboard } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, ErrorText, PageHeader, SEVERITY_STYLE } from "@/components/common";
import { MatchTable } from "@/components/match-table";
import { useMe } from "@/components/app-shell";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const me = useMe();
  const { data, error, reload } = useApi<Dashboard>("/dashboard");

  return (
    <>
      <PageHeader title="ダッシュボード" description={`${me.group_name} — 見えているプロジェクト全体の未対応の脆弱性`} />
      <ErrorText>{error}</ErrorText>
      {data && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
            <Stat label="プロジェクト" value={data.project_count} />
            <Stat label="パッケージ" value={data.package_count} />
            {SEVERITIES.map((s) => (
              <Link key={s} href={`/vulnerabilities/?severity=${s}`}>
                <Stat label={s} value={data.open_counts[s]} className={data.open_counts[s] ? SEVERITY_STYLE[s] : ""} />
              </Link>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle>未対応の脆弱性（重大度順・最新20件）</CardTitle>
            </CardHeader>
            <CardContent>
              {data.recent.length === 0 ? (
                <Empty>
                  未対応の脆弱性はありません。
                  {data.package_count === 0 && (
                    <>
                      {" "}
                      <Link href="/projects/" className="underline">
                        プロジェクト
                      </Link>
                      にパッケージを登録すると監視が始まります。
                    </>
                  )}
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
