"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Company, Department } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ErrorText, OptionSelect, PageHeader, PageTabs } from "@/components/common";
import { useMe } from "@/components/app-shell";
import { CompaniesPanel } from "@/components/admin/companies-panel";
import { DepartmentsPanel } from "@/components/admin/departments-panel";
import { UsersPanel } from "@/components/admin/users-panel";
import { InvitationsPanel } from "@/components/admin/invitations-panel";
import { SystemPanel } from "@/components/admin/system-panel";

type Tab = "companies" | "departments" | "users" | "invitations" | "system";

export default function AdminPage() {
  const t = useTranslations();
  const me = useMe();
  const [tab, setTab] = useState<Tab>(me.role === "group_admin" ? "companies" : "departments");
  const { data: companies, reload: reloadCompanies } = useApi<Company[]>("/companies");
  const { data: departments, reload: reloadDepartments } = useApi<Department[]>("/departments");
  const manageable = (companies ?? []).filter((c) => me.role === "group_admin" || c.id === me.company_id);
  const [picked, setPicked] = useState<string | null>(null);
  const companyId = picked ?? me.company_id ?? manageable[0]?.id ?? "";

  if (!me.can_manage_org) return <ErrorText>{t("admin.adminOnly")}</ErrorText>;
  if (!companies || !departments) return null;

  const companyPicker = tab !== "companies" && tab !== "system" && manageable.length > 1 && (
    <OptionSelect
      value={companyId}
      onValueChange={setPicked}
      options={manageable.map((c) => ({ value: c.id, label: `${c.name}（${t(`labels.companyType.${c.type}`)}）` }))}
    />
  );

  return (
    <>
      <PageHeader title={t("admin.title")} description={t("admin.description", { group: me.group_name })} actions={companyPicker} />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "companies", label: t("admin.tabs.companies") },
          { value: "departments", label: t("admin.tabs.departments") },
          { value: "users", label: t("admin.tabs.users") },
          { value: "invitations", label: t("admin.tabs.invitations") },
          ...(me.role === "group_admin" ? [{ value: "system" as const, label: t("admin.tabs.system") }] : []),
        ]}
      />
      {tab === "companies" && <CompaniesPanel companies={companies} onChanged={reloadCompanies} />}
      {tab === "system" && <SystemPanel />}
      {tab !== "companies" && tab !== "system" && !companyId && <ErrorText>{t("admin.addCompanyFirst")}</ErrorText>}
      {tab === "departments" && companyId && (
        <DepartmentsPanel companies={companies} departments={departments} companyId={companyId} onChanged={reloadDepartments} />
      )}
      {tab === "users" && companyId && (
        <UsersPanel key={companyId} companies={companies} departments={departments} companyId={companyId} />
      )}
      {tab === "invitations" && companyId && (
        <InvitationsPanel key={companyId} companies={companies} departments={departments} companyId={companyId} />
      )}
    </>
  );
}
