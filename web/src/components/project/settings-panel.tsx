"use client";

import { useState } from "react";
import { toast } from "sonner";

import { api, type Department, type Project } from "@/lib/api";
import { departmentPath } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, Select } from "@/components/common";

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
      toast.success("保存しました");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  async function remove() {
    if (prompt(`削除するにはプロジェクト名「${project.name}」を入力してください`) !== project.name) return;
    await api(`/projects/${project.id}`, { method: "DELETE" });
    onDeleted();
  }

  const depts = departments.filter((d) => d.company_id === project.company_id);

  return (
    <div className="grid max-w-xl gap-8">
      <form onSubmit={save} className="grid gap-4">
        <Field label="名前">
          <Input required value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="説明">
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="担当部署">
          <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
            <option value="">（なし）</option>
            {depts.map((d) => (
              <option key={d.id} value={d.id}>
                {departmentPath(departments, d.id)}
              </option>
            ))}
          </Select>
        </Field>
        <div>
          <Button type="submit">保存</Button>
        </div>
      </form>
      <div className="rounded-xl border border-destructive/40 p-4">
        <div className="mb-2 text-sm font-medium text-destructive">プロジェクトの削除</div>
        <p className="mb-3 text-xs text-muted-foreground">パッケージ・検知結果・Webhook もすべて削除されます。</p>
        <Button variant="destructive" onClick={remove}>
          削除する
        </Button>
      </div>
    </div>
  );
}
