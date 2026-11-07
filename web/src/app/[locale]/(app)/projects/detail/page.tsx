"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { useRouter } from "@/i18n/navigation";
import { api, type Company, type Department, type Match, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useMe, usePageCrumb } from "@/components/app-shell";
import { ProjectStatusBadge } from "@/components/sales/status";
import { OverviewPanel, StatusStepper } from "@/components/project/overview-panel";
import { EstimatesPanel } from "@/components/project/estimates-panel";
import { ActivityPanel } from "@/components/project/activity-panel";
import { ActualsPanel } from "@/components/project/actuals-panel";
import { SecurityPanel } from "@/components/project/security-panel";
import { TasksPanel } from "@/components/project/tasks-panel";
import { departmentPath } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { ErrorText, PageHeader, PageTabs, SeverityCountsInline } from "@/components/common";
import { MatchTable } from "@/components/match-table";
import { EolBadge } from "@/components/eol-table";
import { EolPanel } from "@/components/project/eol-panel";
import { PackagesPanel } from "@/components/project/packages-panel";
import { MembersPanel } from "@/components/project/members-panel";
import { WebhooksPanel } from "@/components/project/webhooks-panel";
import { TokensPanel } from "@/components/project/tokens-panel";
import { ReposPanel } from "@/components/project/repos-panel";
import { SettingsPanel } from "@/components/project/settings-panel";

type Tab =
  | "overview"
  | "tasks"
  | "security"
  | "activity"
  | "estimates"
  | "actuals"
  | "vulns" | "eol" | "packages" | "members" | "repos" | "webhooks" | "tokens" | "settings";

function ProjectDetail() {
  const t = useTranslations();
  const id = useSearchParams().get("id");
  const router = useRouter();
  const me = useMe();
  const [tab, setTab] = useState<Tab>("overview");
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
    { value: "overview", label: t("project.tabs.overview") },
    { value: "tasks", label: t("project.tabs.tasks") },
    { value: "security", label: t("project.tabs.security", { count: project.open_security_tasks || "" }) },
    ...(me.is_partner
      ? []
      : [
          { value: "activity" as const, label: t("project.tabs.activity") },
          { value: "estimates" as const, label: t("project.tabs.estimates", { count: project.estimate_count ?? 0 }) },
          { value: "actuals" as const, label: t("project.tabs.actuals") },
        ]),
    { value: "vulns", label: t("project.tabs.vulns") },
    { value: "eol", label: t("project.tabs.eol") },
    { value: "packages", label: t("project.tabs.packages", { count: project.package_count }) },
    { value: "members", label: t("project.tabs.members") },
    ...(canManage
      ? [
          { value: "repos" as const, label: t("project.tabs.repos") },
          { value: "webhooks" as const, label: t("project.tabs.webhooks") },
          { value: "tokens" as const, label: t("project.tabs.tokens") },
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
            <ProjectStatusBadge status={project.status} />
            <span>
              {project.customer ? `${project.customer.name} ・ ` : ""}
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
      <div className="mb-4">
        <StatusStepper project={project} />
      </div>
      <PageTabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "overview" && <OverviewPanel project={project} canManage={canManage} onSaved={reload} />}
      {tab === "tasks" && <TasksPanel project={project} canWrite={canWrite} />}
      {tab === "security" && (
        <SecurityPanel project={project} canWrite={canWrite} canManage={canManage} onChanged={refreshAll} />
      )}
      {tab === "activity" && !me.is_partner && <ActivityPanel project={project} onChanged={reload} />}
      {tab === "estimates" && !me.is_partner && <EstimatesPanel project={project} onChanged={reload} />}
      {tab === "actuals" && !me.is_partner && <ActualsPanel project={project} />}
      {tab === "vulns" && matches && (
        <MatchTable matches={matches} onChanged={refreshAll} canTriage={canWrite} empty={t("project.noMatches")} />
      )}
      {tab === "eol" && <EolPanel projectId={project.id} canWrite={canWrite} onChanged={reload} />}
      {tab === "packages" && <PackagesPanel projectId={project.id} canWrite={canWrite} onChanged={refreshAll} />}
      {tab === "members" && companies && <MembersPanel projectId={project.id} canManage={canManage} companies={companies} />}
      {tab === "repos" && canManage && <ReposPanel projectId={project.id} canManage={canManage} />}
      {tab === "webhooks" && canManage && <WebhooksPanel projectId={project.id} />}
      {tab === "tokens" && canManage && <TokensPanel projectId={project.id} />}
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
