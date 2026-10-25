"use client";

import { useState } from "react";
import { toast } from "sonner";

import { api, type Company, type Department } from "@/lib/api";
import { departmentTree } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, Select } from "@/components/common";

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
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const tree = departmentTree(departments, companyId);
  const company = companies.find((c) => c.id === companyId);

  async function call(fn: () => Promise<unknown>) {
    try {
      await fn();
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="grid gap-4">
      <form
        className="flex flex-wrap items-end gap-2 rounded-xl border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          call(() =>
            api("/departments", { method: "POST", json: { company_id: companyId, name, parent_id: parentId || null } }),
          ).then(() => setName(""));
        }}
      >
        <div className="w-full text-sm font-medium">{company?.name} に部署を追加</div>
        <Select value={parentId} onChange={(e) => setParentId(e.target.value)}>
          <option value="">（最上位）</option>
          {tree.map(({ dept, depth }) => (
            <option key={dept.id} value={dept.id}>
              {"　".repeat(depth)}
              {dept.name}
            </option>
          ))}
        </Select>
        <Input className="max-w-xs" required placeholder="部署名" value={name} onChange={(e) => setName(e.target.value)} />
        <Button type="submit">追加</Button>
      </form>
      {tree.length === 0 ? (
        <Empty>部署がありません</Empty>
      ) : (
        <ul className="divide-y rounded-xl border">
          {tree.map(({ dept, depth }) => (
            <li key={dept.id} className="flex items-center gap-2 px-3 py-2 text-sm">
              <span style={{ paddingLeft: depth * 20 }} className="flex-1">
                {depth > 0 && <span className="mr-1 text-muted-foreground">└</span>}
                {dept.name}
              </span>
              <Select
                value={dept.parent_id ?? ""}
                onChange={(e) =>
                  call(() => api(`/departments/${dept.id}`, { method: "PATCH", json: { parent_id: e.target.value || null } }))
                }
                title="親部署"
              >
                <option value="">（最上位）</option>
                {tree
                  .filter((t) => t.dept.id !== dept.id)
                  .map((t) => (
                    <option key={t.dept.id} value={t.dept.id}>
                      {"　".repeat(t.depth)}
                      {t.dept.name}
                    </option>
                  ))}
              </Select>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const next = prompt("新しい部署名", dept.name);
                  if (next && next !== dept.name) call(() => api(`/departments/${dept.id}`, { method: "PATCH", json: { name: next } }));
                }}
              >
                名前変更
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                onClick={() => confirm(`${dept.name} を削除しますか？`) && call(() => api(`/departments/${dept.id}`, { method: "DELETE" }))}
              >
                削除
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
