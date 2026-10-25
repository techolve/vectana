"use client";

import { useState } from "react";
import { toast } from "sonner";

import { api, COMPANY_TYPE_LABEL, ROLE_LABEL, type Company, type Department, type Me, type User } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { departmentPath } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Field, Select } from "@/components/common";
import { DepartmentPicker } from "@/components/admin/department-picker";
import { useMe } from "@/components/app-shell";

export function UsersPanel({
  companies,
  departments,
  companyId,
}: {
  companies: Company[];
  departments: Department[];
  companyId: string;
}) {
  const { data, reload } = useApi<User[]>(`/users?company_id=${companyId}`);
  const [editing, setEditing] = useState<User | null>(null);
  const [q, setQ] = useState("");
  const company = companies.find((c) => c.id === companyId);
  const needle = q.toLowerCase();
  const rows = (data ?? []).filter(
    (u) => u.company_id === companyId && (!needle || `${u.email} ${u.display_name ?? ""}`.toLowerCase().includes(needle)),
  );

  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <Input className="max-w-xs" placeholder="名前・メールで絞り込み" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="text-xs text-muted-foreground">
          {company?.name}（{company && COMPANY_TYPE_LABEL[company.type]}）: {rows.length} 人
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ユーザー</TableHead>
            <TableHead>ロール</TableHead>
            <TableHead>部署</TableHead>
            <TableHead>状態</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((u) => (
            <TableRow key={u.id}>
              <TableCell>
                <div className="font-medium">{u.display_name || u.email}</div>
                <div className="text-xs text-muted-foreground">{u.email}</div>
              </TableCell>
              <TableCell className="text-xs">{ROLE_LABEL[u.role]}</TableCell>
              <TableCell className="text-xs whitespace-normal">
                {u.departments.map((d) => (
                  <div key={d.department_id}>
                    {departmentPath(departments, d.department_id)}
                    {d.is_primary && <span className="ml-1 text-muted-foreground">(主)</span>}
                    {d.is_head && <span className="ml-1 rounded bg-primary/10 px-1 text-primary">部署長</span>}
                  </div>
                ))}
              </TableCell>
              <TableCell className="text-xs">{u.is_active ? "有効" : <span className="text-destructive">無効</span>}</TableCell>
              <TableCell className="text-right">
                <Button variant="outline" size="sm" onClick={() => setEditing(u)}>
                  編集
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {editing && (
        <EditUserDialog
          user={editing}
          company={company}
          departments={departments}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

export function roleOptions(me: Me, company: Company | undefined): Me["role"][] {
  if (company?.type === "partner") return ["member"];
  return me.role === "group_admin" ? ["group_admin", "company_admin", "member"] : ["company_admin", "member"];
}

function EditUserDialog({
  user,
  company,
  departments,
  onClose,
  onSaved,
}: {
  user: User;
  company: Company | undefined;
  departments: Department[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const me = useMe();
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.is_active);
  const [depts, setDepts] = useState(user.departments);
  const self = user.id === me.id;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/users/${user.id}`, {
        method: "PATCH",
        json: {
          display_name: displayName || null,
          ...(self ? {} : { role, is_active: active }),
          departments: depts,
        },
      });
      toast.success("保存しました");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{user.email}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save} className="grid gap-4">
          <Field label="表示名">
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
          <div className="flex flex-wrap gap-4">
            <Field label="ロール">
              <Select value={role} disabled={self} onChange={(e) => setRole(e.target.value as Me["role"])}>
                {roleOptions(me, company).map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </Select>
            </Field>
            <label className="flex items-center gap-2 self-end pb-1.5 text-sm">
              <input type="checkbox" disabled={self} checked={active} onChange={(e) => setActive(e.target.checked)} />
              ログインを許可
            </label>
          </div>
          {user.company_id && (
            <Field label="所属部署（兼務可）">
              <DepartmentPicker departments={departments} companyId={user.company_id} value={depts} onChange={setDepts} />
            </Field>
          )}
          <DialogFooter>
            <Button type="submit">保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
