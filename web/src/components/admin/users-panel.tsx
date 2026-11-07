"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, hasRole, ROLES, yen, type Company, type Department, type Me, type Role, type User } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { departmentPath } from "@/lib/org";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LabeledField } from "@/components/common";
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
  const t = useTranslations();
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
      <div className="flex flex-wrap items-center gap-2">
        <Input className="max-w-xs" placeholder={t("users.filter")} value={q} onChange={(e) => setQ(e.target.value)} />
        {company && (
          <span className="text-xs text-muted-foreground">
            {t("users.count", {
              company: company.name,
              type: t(`labels.companyType.${company.type}`),
              count: rows.length,
            })}
          </span>
        )}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("users.user")}</TableHead>
            <TableHead>{t("users.role")}</TableHead>
            <TableHead>{t("users.departments")}</TableHead>
            <TableHead className="text-right">{t("users.unitCost")}</TableHead>
            <TableHead>{t("users.state")}</TableHead>
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
              <TableCell className="text-xs">
                <RoleBadges roles={u.roles} />
              </TableCell>
              <TableCell className="text-xs whitespace-normal">
                {u.departments.map((d) => (
                  <div key={d.department_id} className="flex flex-wrap items-center gap-1">
                    {departmentPath(departments, d.department_id)}
                    {d.is_primary && <span className="text-muted-foreground">{t("users.primarySuffix")}</span>}
                    {d.is_head && <Badge variant="secondary">{t("users.head")}</Badge>}
                  </div>
                ))}
              </TableCell>
              <TableCell className="text-right text-xs tabular-nums">{u.unit_cost != null ? yen(u.unit_cost) : "—"}</TableCell>
              <TableCell className="text-xs">
                {u.is_active ? t("common.enabled") : <span className="text-destructive">{t("common.disabled")}</span>}
              </TableCell>
              <TableCell className="text-right">
                <Button variant="outline" size="sm" onClick={() => setEditing(u)}>
                  {t("common.edit")}
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

/** Roles the signed-in admin may hand out. Partner (BP) users get none. */
export function roleOptions(me: Me, company: Company | undefined): Role[] {
  if (company?.type === "partner") return [];
  return hasRole(me, "group_admin") ? ROLES : ROLES.filter((r) => r !== "group_admin");
}

export function RoleBadges({ roles }: { roles: Role[] }) {
  const t = useTranslations();
  if (roles.length === 0) return <span className="text-muted-foreground">{t("labels.role.member")}</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {roles.map((r) => (
        <Badge key={r} variant="secondary">
          {t(`labels.role.${r}`)}
        </Badge>
      ))}
    </span>
  );
}

/** Check one or more roles; roles the caller may not grant stay as they are. */
export function RolesPicker({
  value,
  onChange,
  options,
  disabled,
}: {
  value: Role[];
  onChange: (v: Role[]) => void;
  options: Role[];
  disabled?: boolean;
}) {
  const t = useTranslations();
  if (options.length === 0) return <p className="text-xs text-muted-foreground">{t("users.partnerNoRoles")}</p>;
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2">
      {options.map((r) => (
        <Field key={r} orientation="horizontal" className="w-auto">
          <Checkbox
            id={`role-${r}`}
            disabled={disabled}
            checked={value.includes(r)}
            onCheckedChange={(c) => onChange(c === true ? [...value, r] : value.filter((x) => x !== r))}
          />
          <FieldLabel htmlFor={`role-${r}`} className="font-normal">
            {t(`labels.role.${r}`)}
          </FieldLabel>
        </Field>
      ))}
    </div>
  );
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
  const t = useTranslations();
  const me = useMe();
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [roles, setRoles] = useState<Role[]>(user.roles);
  const [unitCost, setUnitCost] = useState(user.unit_cost?.toString() ?? "");
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
          ...(self ? {} : { roles, is_active: active }),
          unit_cost: unitCost === "" ? null : Number(unitCost),
          departments: depts,
        },
      });
      toast.success(t("common.saved"));
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
        <form onSubmit={save}>
          <FieldGroup>
            <LabeledField label={t("users.displayName")} htmlFor="user-display-name">
              <Input id="user-display-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("users.role")} hint={t("users.roleHint")}>
              <RolesPicker value={roles} onChange={setRoles} options={roleOptions(me, company)} disabled={self} />
            </LabeledField>
            <div className="flex flex-wrap items-end gap-6">
              <LabeledField label={t("users.unitCost")} htmlFor="user-unit-cost" hint={t("users.unitCostHint")}>
                <Input
                  id="user-unit-cost"
                  type="number"
                  min={0}
                  step={1000}
                  className="w-40"
                  value={unitCost}
                  onChange={(e) => setUnitCost(e.target.value)}
                />
              </LabeledField>
              <Field orientation="horizontal" className="w-auto pb-1.5">
                <Checkbox id="user-active" disabled={self} checked={active} onCheckedChange={(c) => setActive(c === true)} />
                <FieldLabel htmlFor="user-active" className="font-normal">
                  {t("users.allowLogin")}
                </FieldLabel>
              </Field>
            </div>
            {user.company_id && (
              <LabeledField label={t("users.departmentsField")}>
                <DepartmentPicker departments={departments} companyId={user.company_id} value={depts} onChange={setDepts} />
              </LabeledField>
            )}
            <DialogFooter>
              <Button type="submit">{t("common.save")}</Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}
