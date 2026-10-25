"use client";

import type { Department, UserDepartment } from "@/lib/api";
import { departmentTree } from "@/lib/org";

/** Pick departments (兼務), the primary one, and which ones the user heads. */
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
  const tree = departmentTree(departments, companyId);
  if (tree.length === 0) return <p className="text-xs text-muted-foreground">この会社には部署がありません</p>;
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
      value.map((v) =>
        v.department_id === id ? { ...v, ...p } : p.is_primary ? { ...v, is_primary: false } : v,
      ),
    );

  return (
    <div className="max-h-64 overflow-y-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-xs text-muted-foreground">
          <tr>
            <th className="px-2 py-1 text-left font-medium">部署</th>
            <th className="px-2 py-1 font-medium">主所属</th>
            <th className="px-2 py-1 font-medium">部署長</th>
          </tr>
        </thead>
        <tbody>
          {tree.map(({ dept, depth }) => {
            const entry = get(dept.id);
            return (
              <tr key={dept.id} className="border-t">
                <td className="px-2 py-1">
                  <label className="flex items-center gap-2" style={{ paddingLeft: depth * 16 }}>
                    <input type="checkbox" checked={!!entry} onChange={(e) => toggle(dept.id, e.target.checked)} />
                    {dept.name}
                  </label>
                </td>
                <td className="px-2 py-1 text-center">
                  <input
                    type="radio"
                    name="primary-department"
                    disabled={!entry}
                    checked={!!entry?.is_primary}
                    onChange={() => patch(dept.id, { is_primary: true })}
                  />
                </td>
                <td className="px-2 py-1 text-center">
                  <input
                    type="checkbox"
                    disabled={!entry}
                    checked={!!entry?.is_head}
                    onChange={(e) => patch(dept.id, { is_head: e.target.checked })}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
