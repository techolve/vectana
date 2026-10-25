"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";

import { api, type Company, type Department, type Match, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { departmentPath } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Empty, ErrorText, PageHeader, SeverityCountsInline, Tabs } from "@/components/common";
import { MatchTable } from "@/components/match-table";
import { PackagesPanel } from "@/components/project/packages-panel";
import { MembersPanel } from "@/components/project/members-panel";
import { WebhooksPanel } from "@/components/project/webhooks-panel";
import { SettingsPanel } from "@/components/project/settings-panel";

type Tab = "vulns" | "packages" | "members" | "webhooks" | "settings";

function ProjectDetail() {
  const id = useSearchParams().get("id");
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("vulns");
  const { data: project, error, reload } = useApi<Project>(id ? `/projects/${id}` : null);
  const { data: matches, reload: reloadMatches } = useApi<Match[]>(id ? `/vulnerabilities?project_id=${id}&status=` : null);
  const { data: companies } = useApi<Company[]>("/companies");
  const { data: departments } = useApi<Department[]>("/departments");

  if (!id) return <ErrorText>プロジェクトが指定されていません</ErrorText>;
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
      toast.success(`${r.packages} 件のパッケージをスキャンしています。少し待ってから再読み込みしてください。`);
      setTimeout(refreshAll, 5000);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const tabs: { value: Tab; label: React.ReactNode }[] = [
    { value: "vulns", label: "脆弱性" },
    { value: "packages", label: `パッケージ (${project.package_count})` },
    { value: "members", label: "メンバー" },
    ...(canManage
      ? [
          { value: "webhooks" as const, label: "通知（Webhook）" },
          { value: "settings" as const, label: "設定" },
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
            <SeverityCountsInline counts={project.open_counts} />
          </span>
        }
        actions={
          canWrite && (
            <Button variant="outline" onClick={scan}>
              <RefreshCwIcon /> 今すぐスキャン
            </Button>
          )
        }
      />
      {project.description && <p className="-mt-3 mb-4 text-sm whitespace-pre-wrap text-muted-foreground">{project.description}</p>}
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "vulns" &&
        matches &&
        (matches.length === 0 ? (
          <Empty>ヒットした脆弱性はありません</Empty>
        ) : (
          <MatchTable matches={matches} onChanged={refreshAll} canTriage={canWrite} />
        ))}
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
