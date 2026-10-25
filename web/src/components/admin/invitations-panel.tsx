"use client";

import { useState } from "react";
import { CopyIcon } from "lucide-react";
import { toast } from "sonner";

import { api, ROLE_LABEL, type Company, type Department, type Invitation, type Me, type UserDepartment } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, Field, formatDate, Select } from "@/components/common";
import { DepartmentPicker } from "@/components/admin/department-picker";
import { roleOptions } from "@/components/admin/users-panel";
import { useMe } from "@/components/app-shell";

export function InvitationsPanel({
  companies,
  departments,
  companyId,
}: {
  companies: Company[];
  departments: Department[];
  companyId: string;
}) {
  const me = useMe();
  const { data, reload } = useApi<Invitation[]>("/invitations");
  const company = companies.find((c) => c.id === companyId);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Me["role"]>("member");
  const [depts, setDepts] = useState<UserDepartment[]>([]);
  const [lastUrl, setLastUrl] = useState<string | null>(null);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    try {
      const inv = await api<Invitation>("/invitations", {
        method: "POST",
        json: { email, display_name: name || null, company_id: companyId, role, departments: depts },
      });
      if (inv.email_sent) {
        toast.success(`${inv.email} に招待メールを送りました`);
        setLastUrl(null);
      } else {
        toast.warning("メールを送れませんでした。下のリンクを直接共有してください。");
        setLastUrl(inv.accept_url ?? null);
      }
      setEmail("");
      setName("");
      setDepts([]);
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const pending = (data ?? []).filter((i) => i.company_id === companyId);

  return (
    <div className="grid gap-4">
      <form onSubmit={invite} className="grid gap-3 rounded-xl border p-4">
        <div className="text-sm font-medium">{company?.name} にユーザーを招待</div>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="メールアドレス">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="表示名（任意）">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="ロール">
            <Select value={role} onChange={(e) => setRole(e.target.value as Me["role"])}>
              {roleOptions(me, company).map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="所属部署（兼務可・任意）">
          <DepartmentPicker departments={departments} companyId={companyId} value={depts} onChange={setDepts} />
        </Field>
        <div>
          <Button type="submit">招待メールを送る</Button>
        </div>
        {lastUrl && (
          <div className="flex items-center gap-2 rounded-lg bg-muted p-2 text-xs">
            <code className="flex-1 break-all">{lastUrl}</code>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => navigator.clipboard.writeText(lastUrl).then(() => toast.success("コピーしました"))}
            >
              <CopyIcon /> コピー
            </Button>
          </div>
        )}
      </form>
      {pending.length === 0 ? (
        <Empty>保留中の招待はありません</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>メール</TableHead>
              <TableHead>ロール</TableHead>
              <TableHead>有効期限</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pending.map((i) => (
              <TableRow key={i.id}>
                <TableCell>{i.email}</TableCell>
                <TableCell className="text-xs">{ROLE_LABEL[i.role as Me["role"]] ?? i.role}</TableCell>
                <TableCell className="text-xs">{formatDate(i.expires_at)}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={async () => {
                      await api(`/invitations/${i.id}`, { method: "DELETE" });
                      reload();
                    }}
                  >
                    取り消し
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
