"use client";

import { useState } from "react";

import { COMPANY_TYPE_LABEL, type Company, type Department } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ErrorText, PageHeader, Select, Tabs } from "@/components/common";
import { useMe } from "@/components/app-shell";
import { CompaniesPanel } from "@/components/admin/companies-panel";
import { DepartmentsPanel } from "@/components/admin/departments-panel";
import { UsersPanel } from "@/components/admin/users-panel";
import { InvitationsPanel } from "@/components/admin/invitations-panel";

type Tab = "companies" | "departments" | "users" | "invitations";

export default function AdminPage() {
  const me = useMe();
  const [tab, setTab] = useState<Tab>(me.role === "group_admin" ? "companies" : "departments");
  const { data: companies, reload: reloadCompanies } = useApi<Company[]>("/companies");
  const { data: departments, reload: reloadDepartments } = useApi<Department[]>("/departments");
  const manageable = (companies ?? []).filter((c) => me.role === "group_admin" || c.id === me.company_id);
  const [picked, setPicked] = useState<string | null>(null);
  const companyId = picked ?? me.company_id ?? manageable[0]?.id ?? "";

  if (!me.can_manage_org) return <ErrorText>管理者のみ利用できます</ErrorText>;
  if (!companies || !departments) return null;

  const companyPicker = tab !== "companies" && manageable.length > 1 && (
    <Select value={companyId} onChange={(e) => setPicked(e.target.value)}>
      {manageable.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}（{COMPANY_TYPE_LABEL[c.type]}）
        </option>
      ))}
    </Select>
  );

  return (
    <>
      <PageHeader title="組織管理" description={`${me.group_name} の会社・部署・ユーザー`} actions={companyPicker} />
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "companies", label: "会社" },
          { value: "departments", label: "部署" },
          { value: "users", label: "ユーザー" },
          { value: "invitations", label: "招待" },
        ]}
      />
      {tab === "companies" && <CompaniesPanel companies={companies} onChanged={reloadCompanies} />}
      {tab !== "companies" && !companyId && <ErrorText>先に会社を追加してください</ErrorText>}
      {tab === "departments" && companyId && (
        <DepartmentsPanel companies={companies} departments={departments} companyId={companyId} onChanged={reloadDepartments} />
      )}
      {tab === "users" && companyId && <UsersPanel key={companyId} companies={companies} departments={departments} companyId={companyId} />}
      {tab === "invitations" && companyId && (
        <InvitationsPanel key={companyId} companies={companies} departments={departments} companyId={companyId} />
      )}
    </>
  );
}
