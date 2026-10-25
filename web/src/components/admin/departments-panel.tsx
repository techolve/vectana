"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type Company, type Department } from "@/lib/api";
import { departmentTree } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, OptionSelect } from "@/components/common";

export function DepartmentsPanel({
  companies,
  departments,
  companyId,
  onChanged,
}: {
  companies: Company[];
  departments: Department[];
  companyId: string;
  onChanged: () => void;
}) {
  const t = useTranslations();
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const tree = departmentTree(departments, companyId);
  const company = companies.find((c) => c.id === companyId);
  const indent = (depth: number) => "　".repeat(depth);

  async function call(fn: () => Promise<unknown>) {
    try {
      await fn();
      onChanged();
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    }
  }

  return (
    <div className="grid gap-4">
      <form
        className="flex flex-wrap items-end gap-2 rounded-xl border p-3"
        onSubmit={async (e) => {
          e.preventDefault();
          if (
            await call(() =>
              api("/departments", { method: "POST", json: { company_id: companyId, name, parent_id: parentId || null } }),
            )
          )
            setName("");
        }}
      >
        <div className="w-full text-sm font-medium">{t("departments.addTo", { company: company?.name ?? "" })}</div>
        <OptionSelect
          value={parentId}
          onValueChange={setParentId}
          options={[
            { value: "", label: t("departments.top") },
            ...tree.map(({ dept, depth }) => ({ value: dept.id, label: `${indent(depth)}${dept.name}` })),
          ]}
        />
        <Input className="max-w-xs" required placeholder={t("departments.name")} value={name} onChange={(e) => setName(e.target.value)} />
        <Button type="submit">{t("common.add")}</Button>
      </form>
      {tree.length === 0 ? (
        <Empty>{t("departments.empty")}</Empty>
      ) : (
        <ul className="divide-y rounded-xl border">
          {tree.map(({ dept, depth }) => (
            <li key={dept.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
              <span style={{ paddingLeft: depth * 20 }} className="flex-1">
                {depth > 0 && <span className="mr-1 text-muted-foreground">└</span>}
                {dept.name}
              </span>
              <OptionSelect
                value={dept.parent_id ?? ""}
                title={t("departments.parent")}
                onValueChange={(v) =>
                  call(() => api(`/departments/${dept.id}`, { method: "PATCH", json: { parent_id: v || null } }))
                }
                options={[
                  { value: "", label: t("departments.top") },
                  ...tree
                    .filter((x) => x.dept.id !== dept.id)
                    .map((x) => ({ value: x.dept.id, label: `${indent(x.depth)}${x.dept.name}` })),
                ]}
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const next = prompt(t("departments.newName"), dept.name);
                  if (next && next !== dept.name)
                    call(() => api(`/departments/${dept.id}`, { method: "PATCH", json: { name: next } }));
                }}
              >
                {t("common.rename")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                onClick={() =>
                  confirm(t("departments.confirmDelete", { name: dept.name })) &&
                  call(() => api(`/departments/${dept.id}`, { method: "DELETE" }))
                }
              >
                {t("common.delete")}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
