"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type Department, type Project } from "@/lib/api";
import { departmentPath } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { LabeledField, OptionSelect } from "@/components/common";

export function SettingsPanel({
  project,
  departments,
  onSaved,
  onDeleted,
}: {
  project: Project;
  departments: Department[];
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const t = useTranslations();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const [departmentId, setDepartmentId] = useState(project.department_id ?? "");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/projects/${project.id}`, {
        method: "PATCH",
        json: { name, description: description || null, department_id: departmentId || null },
      });
      toast.success(t("common.saved"));
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function remove() {
    if (prompt(t("projectSettings.confirmDelete", { name: project.name })) !== project.name) return;
    await api(`/projects/${project.id}`, { method: "DELETE" });
    onDeleted();
  }

  const depts = departments.filter((d) => d.company_id === project.company_id);

  return (
    <div className="grid max-w-xl gap-8">
      <form onSubmit={save}>
        <FieldGroup>
          <LabeledField label={t("projectSettings.name")} htmlFor="settings-name">
            <Input id="settings-name" required value={name} onChange={(e) => setName(e.target.value)} />
          </LabeledField>
          <LabeledField label={t("projectSettings.description")} htmlFor="settings-description">
            <Textarea id="settings-description" value={description} onChange={(e) => setDescription(e.target.value)} />
          </LabeledField>
          <LabeledField label={t("projectSettings.department")}>
            <OptionSelect
              value={departmentId}
              onValueChange={setDepartmentId}
              options={[
                { value: "", label: t("common.noneOption") },
                ...depts.map((d) => ({ value: d.id, label: departmentPath(departments, d.id) })),
              ]}
            />
          </LabeledField>
          <div>
            <Button type="submit">{t("common.save")}</Button>
          </div>
        </FieldGroup>
      </form>
      <div className="rounded-xl border border-destructive/40 p-4">
        <div className="mb-2 text-sm font-medium text-destructive">{t("projectSettings.dangerTitle")}</div>
        <p className="mb-3 text-xs text-muted-foreground">{t("projectSettings.dangerDescription")}</p>
        <Button variant="destructive" onClick={remove}>
          {t("projectSettings.deleteButton")}
        </Button>
      </div>
    </div>
  );
}
