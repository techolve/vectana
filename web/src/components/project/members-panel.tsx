"use client";

import { useEffect, useState } from "react";
import { Trash2Icon } from "lucide-react";
import { toast } from "sonner";

import { api, PROJECT_ROLE_LABEL, type Company, type Member, type ProjectRole, type UserBrief } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, Select } from "@/components/common";

export function MembersPanel({
  projectId,
  canManage,
  companies,
}: {
  projectId: string;
  canManage: boolean;
  companies: Company[];
}) {
  const { data, reload } = useApi<Member[]>(`/projects/${projectId}/members`);
  const company = (id: string | null) => companies.find((c) => c.id === id);
  const isPartner = (id: string | null) => company(id)?.type === "partner";

  async function setRole(m: Member, role: ProjectRole) {
    try {
      await api(`/projects/${projectId}/members/${m.id}`, { method: "PATCH", json: { role } });
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function remove(m: Member) {
    if (!confirm(`${m.display_name || m.email} のアサインを解除しますか？`)) return;
    await api(`/projects/${projectId}/members/${m.id}`, { method: "DELETE" });
    reload();
  }

  return (
    <div className="grid gap-4">
      {canManage && <AssignForm projectId={projectId} companies={companies} onAdded={reload} existing={data ?? []} />}
      {data &&
        (data.length === 0 ? (
          <Empty>アサインされたメンバーはいません</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>メンバー</TableHead>
                <TableHead>会社</TableHead>
                <TableHead>ロール</TableHead>
                {canManage && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>
                    <div className="font-medium">{m.display_name || m.email}</div>
                    <div className="text-xs text-muted-foreground">{m.email}</div>
                  </TableCell>
                  <TableCell className="text-xs">
                    {company(m.company_id)?.name ?? "-"}
                    {isPartner(m.company_id) && <span className="ml-1 rounded bg-muted px-1">BP</span>}
                  </TableCell>
                  <TableCell>
                    {canManage ? (
                      <Select value={m.role} onChange={(e) => setRole(m, e.target.value as ProjectRole)}>
                        {(Object.keys(PROJECT_ROLE_LABEL) as ProjectRole[])
                          .filter((r) => r !== "owner" || !isPartner(m.company_id))
                          .map((r) => (
                            <option key={r} value={r}>
                              {PROJECT_ROLE_LABEL[r]}
                            </option>
                          ))}
                      </Select>
                    ) : (
                      PROJECT_ROLE_LABEL[m.role]
                    )}
                  </TableCell>
                  {canManage && (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon-sm" onClick={() => remove(m)} title="解除">
                        <Trash2Icon />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      <p className="text-xs text-muted-foreground">
        アサインされたメンバーには、個人設定に応じて脆弱性の通知メールが届きます。BP（協力会社）はアサインされたプロジェクトだけが見えます。
      </p>
    </div>
  );
}

function AssignForm({
  projectId,
  companies,
  onAdded,
  existing,
}: {
  projectId: string;
  companies: Company[];
  onAdded: () => void;
  existing: Member[];
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<UserBrief[]>([]);
  const [role, setRole] = useState<ProjectRole>("member");

  useEffect(() => {
    const t = setTimeout(() => {
      api<UserBrief[]>(`/users/directory?q=${encodeURIComponent(q)}`)
        .then(setResults)
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const assigned = new Set(existing.map((m) => m.user_id));

  async function add(u: UserBrief) {
    try {
      await api(`/projects/${projectId}/members`, { method: "POST", json: { user_id: u.id, role } });
      toast.success(`${u.display_name || u.email} をアサインしました`);
      onAdded();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="grid gap-2 rounded-xl border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">メンバーをアサイン</span>
        <Input className="max-w-xs" placeholder="名前・メールで検索" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={role} onChange={(e) => setRole(e.target.value as ProjectRole)}>
          {(Object.keys(PROJECT_ROLE_LABEL) as ProjectRole[]).map((r) => (
            <option key={r} value={r}>
              {PROJECT_ROLE_LABEL[r]}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex flex-wrap gap-2">
        {results
          .filter((u) => !assigned.has(u.id))
          .slice(0, 12)
          .map((u) => (
            <Button key={u.id} variant="outline" size="sm" onClick={() => add(u)}>
              + {u.display_name || u.email}
              <span className="text-muted-foreground">{companies.find((c) => c.id === u.company_id)?.name}</span>
            </Button>
          ))}
      </div>
    </div>
  );
}
