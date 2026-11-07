"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { SEVERITIES, type Match } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Input } from "@/components/ui/input";
import { ErrorText, OptionSelect, PageHeader } from "@/components/common";
import { MatchTable } from "@/components/match-table";

function VulnerabilityList() {
  const t = useTranslations();
  const params = useSearchParams();
  const [severity, setSeverity] = useState(params.get("severity") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "open");
  const [assignee, setAssignee] = useState(params.get("assignee") ?? "");
  const [overdue, setOverdue] = useState(params.get("overdue") === "true" ? "true" : "");
  const [q, setQ] = useState("");
  const query = new URLSearchParams();
  if (severity) query.set("severity", severity);
  query.set("status", status);
  if (assignee) query.set("assignee", assignee);
  if (overdue) query.set("overdue", "true");
  const { data, error, reload } = useApi<Match[]>(`/vulnerabilities?${query}`);

  const needle = q.trim().toLowerCase();
  const filtered = (data ?? []).filter(
    (m) =>
      !needle ||
      [
        m.project_name,
        m.package_name,
        m.vuln_id,
        ...m.aliases,
        m.summary ?? "",
        m.assignee?.display_name ?? "",
        m.assignee?.email ?? "",
      ].some((s) => s.toLowerCase().includes(needle)),
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
              // "open,ack" = still needs action; "" = everything.
              options={[
                { value: "open", label: t("labels.status.open") },
                { value: "open,ack", label: t("vulns.status.unresolved") },
                { value: "ack", label: t("labels.status.ack") },
                { value: "ignored", label: t("labels.status.ignored") },
                { value: "", label: t("vulns.status.all") },
              ]}
            />
            <OptionSelect
              value={assignee}
              onValueChange={setAssignee}
              options={[
                { value: "", label: t("vulns.allAssignees") },
                { value: "me", label: t("vulns.assignedToMe") },
                { value: "none", label: t("triage.unassigned") },
              ]}
            />
            <OptionSelect
              value={overdue}
              onValueChange={setOverdue}
              options={[
                { value: "", label: t("vulns.anyDueDate") },
                { value: "true", label: t("triage.overdue") },
              ]}
            />
          </>
        }
      />
      <ErrorText>{error}</ErrorText>
      {data && <MatchTable matches={filtered} onChanged={reload} showProject empty={t("vulns.empty")} />}
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
