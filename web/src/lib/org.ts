import type { Department } from "@/lib/api";

/** "開発本部 / 第1開発部" */
export function departmentPath(departments: Department[], id: string): string {
  const byId = new Map(departments.map((d) => [d.id, d]));
  const parts: string[] = [];
  let current = byId.get(id);
  const seen = new Set<string>();
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    parts.unshift(current.name);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return parts.join(" / ");
}

/** Departments of one company in tree order with depth, for indented lists. */
export function departmentTree(departments: Department[], companyId: string) {
  const own = departments.filter((d) => d.company_id === companyId);
  const children = new Map<string | null, Department[]>();
  for (const d of own) {
    const key = d.parent_id && own.some((p) => p.id === d.parent_id) ? d.parent_id : null;
    children.set(key, [...(children.get(key) ?? []), d]);
  }
  const out: { dept: Department; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const d of (children.get(parent) ?? []).sort((a, b) => a.name.localeCompare(b.name, "ja"))) {
      out.push({ dept: d, depth });
      walk(d.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}
