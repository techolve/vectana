"use client";

import { useState } from "react";
import { CopyIcon } from "lucide-react";
import { toast } from "sonner";
import { useLocale, useTranslations } from "next-intl";

import { api, type Company, type Department, type Invitation, type Me, type UserDepartment } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { routing } from "@/i18n/routing";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, LabeledField, OptionSelect, useFormatDate } from "@/components/common";
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
  const t = useTranslations();
  const me = useMe();
  const formatDate = useFormatDate();
  const localeOptions = routing.locales.map((l) => ({ value: l, label: t(`locales.${l}`) }));
  const { data, reload } = useApi<Invitation[]>("/invitations");
  const company = companies.find((c) => c.id === companyId);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<string>("member");
  const [depts, setDepts] = useState<UserDepartment[]>([]);
  const [lastUrl, setLastUrl] = useState<string | null>(null);
  const [inviteLocale, setInviteLocale] = useState<string>(useLocale());

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    try {
      const inv = await api<Invitation>("/invitations", {
        method: "POST",
        json: { email, display_name: name || null, company_id: companyId, role, departments: depts, locale: inviteLocale },
      });
      if (inv.email_sent) {
        toast.success(t("invitations.sent", { email: inv.email }));
        setLastUrl(null);
      } else {
        toast.warning(t("invitations.notSent"));
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
      <form onSubmit={invite} className="rounded-xl border p-4">
        <FieldGroup>
          <div className="text-sm font-medium">{t("invitations.inviteTo", { company: company?.name ?? "" })}</div>
          <div className="grid gap-4 md:grid-cols-4">
            <LabeledField label={t("invitations.email")} htmlFor="invite-email">
              <Input id="invite-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("invitations.displayName")} htmlFor="invite-name">
              <Input id="invite-name" value={name} onChange={(e) => setName(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("invitations.role")}>
              <OptionSelect
                value={role}
                onValueChange={setRole}
                options={roleOptions(me, company).map((r) => ({ value: r, label: t(`labels.role.${r}`) }))}
              />
            </LabeledField>
            <LabeledField label={t("invitations.language")}>
              <OptionSelect value={inviteLocale} onValueChange={setInviteLocale} options={localeOptions} />
            </LabeledField>
          </div>
          <LabeledField label={t("invitations.departments")}>
            <DepartmentPicker departments={departments} companyId={companyId} value={depts} onChange={setDepts} />
          </LabeledField>
          <div>
            <Button type="submit">{t("invitations.send")}</Button>
          </div>
          {lastUrl && (
            <div className="flex items-center gap-2 rounded-lg bg-muted p-2 text-xs">
              <code className="flex-1 break-all">{lastUrl}</code>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => navigator.clipboard.writeText(lastUrl).then(() => toast.success(t("common.copied")))}
              >
                <CopyIcon /> {t("common.copy")}
              </Button>
            </div>
          )}
        </FieldGroup>
      </form>
      {pending.length === 0 ? (
        <Empty>{t("invitations.empty")}</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("invitations.email")}</TableHead>
              <TableHead>{t("invitations.role")}</TableHead>
              <TableHead>{t("invitations.expires")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pending.map((i) => (
              <TableRow key={i.id}>
                <TableCell>{i.email}</TableCell>
                <TableCell className="text-xs">{t(`labels.role.${i.role as Me["role"]}`)}</TableCell>
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
                    {t("invitations.revoke")}
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
