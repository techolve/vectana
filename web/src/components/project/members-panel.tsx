"use client";

import { useEffect, useState } from "react";
import { Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type Company, type Member, type ProjectRole, type UserBrief } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, OptionSelect } from "@/components/common";

const ROLES: ProjectRole[] = ["owner", "member", "viewer"];

export function MembersPanel({
  projectId,
  canManage,
  companies,
}: {
  projectId: string;
  canManage: boolean;
  companies: Company[];
}) {
  const t = useTranslations();
  const { data, reload } = useApi<Member[]>(`/projects/${projectId}/members`);
  const company = (id: string | null) => companies.find((c) => c.id === id);
  const isPartner = (id: string | null) => company(id)?.type === "partner";

  async function setRole(m: Member, role: string) {
    try {
      await api(`/projects/${projectId}/members/${m.id}`, { method: "PATCH", json: { role } });
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function remove(m: Member) {
    if (!confirm(t("members.confirmRemove", { name: m.display_name || m.email }))) return;
    await api(`/projects/${projectId}/members/${m.id}`, { method: "DELETE" });
    reload();
  }

  return (
    <div className="grid gap-4">
      {canManage && <AssignForm projectId={projectId} companies={companies} onAdded={reload} existing={data ?? []} />}
      {data &&
        (data.length === 0 ? (
          <Empty>{t("members.empty")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("members.member")}</TableHead>
                <TableHead>{t("members.company")}</TableHead>
                <TableHead>{t("members.role")}</TableHead>
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
                    {isPartner(m.company_id) && (
                      <Badge variant="secondary" className="ml-1">
                        {t("labels.partner")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {canManage ? (
                      <OptionSelect
                        value={m.role}
                        onValueChange={(v) => setRole(m, v)}
                        options={ROLES.filter((r) => r !== "owner" || !isPartner(m.company_id)).map((r) => ({
                          value: r,
                          label: t(`labels.projectRole.${r}`),
                        }))}
                      />
                    ) : (
                      t(`labels.projectRole.${m.role}`)
                    )}
                  </TableCell>
                  {canManage && (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon-sm" onClick={() => remove(m)} title={t("common.remove")}>
                        <Trash2Icon />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      <p className="text-xs text-muted-foreground">{t("members.note")}</p>
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
  const t = useTranslations();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<UserBrief[]>([]);
  const [role, setRole] = useState<string>("member");

  useEffect(() => {
    const timer = setTimeout(() => {
      api<UserBrief[]>(`/users/directory?q=${encodeURIComponent(q)}`)
        .then(setResults)
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [q]);

  const assigned = new Set(existing.map((m) => m.user_id));

  async function add(u: UserBrief) {
    try {
      await api(`/projects/${projectId}/members`, { method: "POST", json: { user_id: u.id, role } });
      toast.success(t("members.assigned", { name: u.display_name || u.email }));
      onAdded();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="grid gap-2 rounded-xl border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t("members.assign")}</span>
        <Input className="max-w-xs" placeholder={t("members.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <OptionSelect
          value={role}
          onValueChange={setRole}
          options={ROLES.map((r) => ({ value: r, label: t(`labels.projectRole.${r}`) }))}
        />
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
