"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PlusIcon } from "lucide-react";

import { api, type Company, type Department, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorText, Field, PageHeader, Select, SeverityCountsInline } from "@/components/common";
import { useMe } from "@/components/app-shell";
import { departmentPath } from "@/lib/org";

export default function ProjectsPage() {
  const me = useMe();
  const { data, error } = useApi<Project[]>("/projects");
  const { data: companies } = useApi<Company[]>("/companies");
  const { data: departments } = useApi<Department[]>("/departments");
  const [open, setOpen] = useState(false);

  const companyName = (id: string) => companies?.find((c) => c.id === id)?.name ?? "";

  return (
    <>
      <PageHeader
        title="プロジェクト"
        description="見えているプロジェクト（アサイン先・管理範囲）"
        actions={
          !me.is_partner && (
            <Button onClick={() => setOpen(true)}>
              <PlusIcon /> 新規作成
            </Button>
          )
        }
      />
      <ErrorText>{error}</ErrorText>
      {data &&
        (data.length === 0 ? (
          <Empty>プロジェクトがありません</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名前</TableHead>
                <TableHead>会社 / 部署</TableHead>
                <TableHead className="text-right">パッケージ</TableHead>
                <TableHead>未対応の脆弱性</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Link href={`/projects/detail/?id=${p.id}`} className="font-medium hover:underline">
                      {p.name}
                    </Link>
                    {p.description && <div className="max-w-sm truncate text-xs text-muted-foreground">{p.description}</div>}
                  </TableCell>
                  <TableCell className="text-xs">
                    {companyName(p.company_id)}
                    {p.department_id && departments && (
                      <div className="text-muted-foreground">{departmentPath(departments, p.department_id)}</div>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{p.package_count}</TableCell>
                  <TableCell>
                    <SeverityCountsInline counts={p.open_counts} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      {companies && departments && (
        <CreateProjectDialog open={open} onOpenChange={setOpen} companies={companies} departments={departments} />
      )}
    </>
  );
}

function CreateProjectDialog({
  open,
  onOpenChange,
  companies,
  departments,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  companies: Company[];
  departments: Department[];
}) {
  const me = useMe();
  const router = useRouter();
  const selectable = companies.filter(
    (c) => c.type !== "partner" && (me.role === "group_admin" || c.id === me.company_id),
  );
  const [companyId, setCompanyId] = useState(me.company_id ?? selectable[0]?.id ?? "");
  const [departmentId, setDepartmentId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const p = await api<Project>("/projects", {
        method: "POST",
        json: { name, description: description || null, company_id: companyId, department_id: departmentId || null },
      });
      router.push(`/projects/detail/?id=${p.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const depts = departments.filter((d) => d.company_id === companyId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>プロジェクトを作成</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <Field label="名前">
            <Input required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="説明">
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <Field label="会社">
            <Select
              value={companyId}
              onChange={(e) => {
                setCompanyId(e.target.value);
                setDepartmentId("");
              }}
            >
              {selectable.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="担当部署" hint="部署長は配下のプロジェクトを閲覧・管理できます">
            <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
              <option value="">（なし）</option>
              {depts.map((d) => (
                <option key={d.id} value={d.id}>
                  {departmentPath(departments, d.id)}
                </option>
              ))}
            </Select>
          </Field>
          <ErrorText>{error}</ErrorText>
          <DialogFooter>
            <Button type="submit" disabled={!companyId}>
              作成
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
