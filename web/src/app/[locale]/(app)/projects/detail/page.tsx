"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { useRouter } from "@/i18n/navigation";
import { api, type Company, type Department, type Match, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { usePageCrumb } from "@/components/app-shell";
import { departmentPath } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Empty, ErrorText, PageHeader, PageTabs, SeverityCountsInline } from "@/components/common";
import { MatchTable } from "@/components/match-table";
import { EolBadge } from "@/components/eol-table";
import { EolPanel } from "@/components/project/eol-panel";
import { PackagesPanel } from "@/components/project/packages-panel";
import { MembersPanel } from "@/components/project/members-panel";
import { WebhooksPanel } from "@/components/project/webhooks-panel";
import { SettingsPanel } from "@/components/project/settings-panel";

type Tab = "vulns" | "eol" | "packages" | "members" | "webhooks" | "settings";

function ProjectDetail() {
  const t = useTranslations();
  const id = useSearchParams().get("id");
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("vulns");
  const { data: project, error, reload } = useApi<Project>(id ? `/projects/${id}` : null);
  const { data: matches, reload: reloadMatches } = useApi<Match[]>(id ? `/vulnerabilities?project_id=${id}&status=` : null);
  const { data: companies } = useApi<Company[]>("/companies");
  const { data: departments } = useApi<Department[]>("/departments");
  usePageCrumb(project?.name);

  if (!id) return <ErrorText>{t("project.notSpecified")}</ErrorText>;
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!project) return null;

  const canWrite = project.my_level === "write" || project.my_level === "manage";
  const canManage = project.my_level === "manage";
  const company = companies?.find((c) => c.id === project.company_id);
  const refreshAll = () => {
    reload();
    reloadMatches();
  };

  async function scan() {
    try {
      const r = await api<{ packages: number }>(`/projects/${id}/scan`, { method: "POST" });
      toast.success(t("project.scanStarted", { count: r.packages }));
      setTimeout(refreshAll, 5000);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const tabs: { value: Tab; label: React.ReactNode }[] = [
    { value: "vulns", label: t("project.tabs.vulns") },
    { value: "eol", label: t("project.tabs.eol") },
    { value: "packages", label: t("project.tabs.packages", { count: project.package_count }) },
    { value: "members", label: t("project.tabs.members") },
    ...(canManage
      ? [
          { value: "webhooks" as const, label: t("project.tabs.webhooks") },
          { value: "settings" as const, label: t("project.tabs.settings") },
        ]
      : []),
  ];

  return (
    <>
      <PageHeader
        title={project.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>
              {company?.name}
              {project.department_id && departments ? ` / ${departmentPath(departments, project.department_id)}` : ""}
            </span>
            <SeverityCountsInline counts={project.open_counts} empty={t("common.none")} />
            {project.eol_counts.eol > 0 && <EolBadge status="eol" />}
            {project.eol_counts.approaching > 0 && <EolBadge status="approaching" />}
          </span>
        }
        actions={
          canWrite && (
            <Button variant="outline" onClick={scan}>
              <RefreshCwIcon /> {t("project.scanNow")}
            </Button>
          )
        }
      />
      {project.description && (
        <p className="-mt-3 mb-4 text-sm whitespace-pre-wrap text-muted-foreground">{project.description}</p>
      )}
      <PageTabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "vulns" &&
        matches &&
        (matches.length === 0 ? (
          <Empty>{t("project.noMatches")}</Empty>
        ) : (
          <MatchTable matches={matches} onChanged={refreshAll} canTriage={canWrite} />
        ))}
      {tab === "eol" && <EolPanel projectId={project.id} canWrite={canWrite} onChanged={reload} />}
      {tab === "packages" && <PackagesPanel projectId={project.id} canWrite={canWrite} onChanged={refreshAll} />}
      {tab === "members" && companies && <MembersPanel projectId={project.id} canManage={canManage} companies={companies} />}
      {tab === "webhooks" && canManage && <WebhooksPanel projectId={project.id} />}
      {tab === "settings" && canManage && departments && (
        <SettingsPanel
          project={project}
          departments={departments}
          onSaved={reload}
          onDeleted={() => router.replace("/projects/")}
        />
      )}
    </>
  );
}

export default function ProjectDetailPage() {
  return (
    <Suspense>
      <ProjectDetail />
    </Suspense>
  );
}
