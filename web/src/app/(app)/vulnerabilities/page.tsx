"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

import { SEVERITIES, STATUS_LABEL, type Match } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Empty, ErrorText, PageHeader, Select } from "@/components/common";
import { MatchTable } from "@/components/match-table";

function VulnerabilityList() {
  const params = useSearchParams();
  const [severity, setSeverity] = useState(params.get("severity") ?? "");
  const [status, setStatus] = useState("open");
  const [q, setQ] = useState("");
  const query = new URLSearchParams();
  if (severity) query.set("severity", severity);
  query.set("status", status);
  const { data, error, reload } = useApi<Match[]>(`/vulnerabilities?${query}`);

  const needle = q.trim().toLowerCase();
  const filtered = (data ?? []).filter(
    (m) =>
      !needle ||
      [m.project_name, m.package_name, m.vuln_id, ...m.aliases, m.summary ?? ""].some((s) =>
        s.toLowerCase().includes(needle),
      ),
  );

  return (
    <>
      <PageHeader
        title="脆弱性"
        description="見えているプロジェクトでヒットした脆弱性の一覧"
        actions={
          <>
            <input
              placeholder="キーワード"
              className="h-8 rounded-lg border border-input bg-background px-2 text-sm dark:bg-input/30"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">すべての重大度</option>
              {SEVERITIES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(STATUS_LABEL).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </>
        }
      />
      <ErrorText>{error}</ErrorText>
      {data && (filtered.length === 0 ? <Empty>該当する脆弱性はありません</Empty> : <MatchTable matches={filtered} onChanged={reload} showProject />)}
    </>
  );
}

export default function VulnerabilitiesPage() {
  return (
    <Suspense>
      <VulnerabilityList />
    </Suspense>
  );
}
