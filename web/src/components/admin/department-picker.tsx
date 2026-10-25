"use client";

import { useTranslations } from "next-intl";

import type { Department, UserDepartment } from "@/lib/api";
import { departmentTree } from "@/lib/org";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

/** Pick departments (multiple allowed), the primary one, and which ones the user heads. */
export function DepartmentPicker({
  departments,
  companyId,
  value,
  onChange,
}: {
  departments: Department[];
  companyId: string;
  value: UserDepartment[];
  onChange: (v: UserDepartment[]) => void;
}) {
  const t = useTranslations("departments");
  const tree = departmentTree(departments, companyId);
  if (tree.length === 0) return <p className="text-xs text-muted-foreground">{t("noneInCompany")}</p>;
  const get = (id: string) => value.find((v) => v.department_id === id);

  const toggle = (id: string, on: boolean) => {
    if (on) {
      onChange([...value, { department_id: id, is_primary: value.length === 0, is_head: false }]);
    } else {
      const rest = value.filter((v) => v.department_id !== id);
      if (rest.length && !rest.some((v) => v.is_primary)) rest[0] = { ...rest[0], is_primary: true };
      onChange(rest);
    }
  };
  const patch = (id: string, p: Partial<UserDepartment>) =>
    onChange(
      value.map((v) => (v.department_id === id ? { ...v, ...p } : p.is_primary ? { ...v, is_primary: false } : v)),
    );

  return (
    <div className="max-h-64 overflow-y-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("column")}</TableHead>
            <TableHead className="text-center">{t("primary")}</TableHead>
            <TableHead className="text-center">{t("head")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tree.map(({ dept, depth }) => {
            const entry = get(dept.id);
            return (
              <TableRow key={dept.id}>
                <TableCell>
                  <label className="flex items-center gap-2" style={{ paddingLeft: depth * 16 }}>
                    <Checkbox checked={!!entry} onCheckedChange={(checked) => toggle(dept.id, checked === true)} />
                    {dept.name}
                  </label>
                </TableCell>
                <TableCell className="text-center">
                  <input
                    type="radio"
                    name="primary-department"
                    className="accent-primary"
                    disabled={!entry}
                    checked={!!entry?.is_primary}
                    onChange={() => patch(dept.id, { is_primary: true })}
                  />
                </TableCell>
                <TableCell className="text-center">
                  <Checkbox
                    disabled={!entry}
                    checked={!!entry?.is_head}
                    onCheckedChange={(checked) => patch(dept.id, { is_head: checked === true })}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
