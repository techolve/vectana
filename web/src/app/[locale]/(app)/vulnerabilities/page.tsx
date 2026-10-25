"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { SEVERITIES, type Match } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Input } from "@/components/ui/input";
import { Empty, ErrorText, OptionSelect, PageHeader } from "@/components/common";
import { MatchTable } from "@/components/match-table";

const STATUSES = ["open", "ack", "ignored"] as const;

function VulnerabilityList() {
  const t = useTranslations();
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
        title={t("vulns.title")}
        description={t("vulns.description")}
        actions={
          <>
            <Input className="w-48" placeholder={t("common.keyword")} value={q} onChange={(e) => setQ(e.target.value)} />
            <OptionSelect
              value={severity}
              onValueChange={setSeverity}
              options={[{ value: "", label: t("vulns.allSeverities") }, ...SEVERITIES.map((s) => ({ value: s, label: s }))]}
            />
            <OptionSelect
              value={status}
              onValueChange={setStatus}
              options={STATUSES.map((s) => ({ value: s, label: t(`labels.status.${s}`) }))}
            />
          </>
        }
      />
      <ErrorText>{error}</ErrorText>
      {data &&
        (filtered.length === 0 ? (
          <Empty>{t("vulns.empty")}</Empty>
        ) : (
          <MatchTable matches={filtered} onChanged={reload} showProject />
        ))}
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
