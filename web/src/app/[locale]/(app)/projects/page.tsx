"use client";

import { useState } from "react";
import { PlusIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/navigation";
import { api, type Company, type Department, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { departmentPath } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Empty,
  ErrorText,
  LabeledField,
  OptionSelect,
  PageHeader,
  SeverityCountsInline,
} from "@/components/common";
import { useMe } from "@/components/app-shell";

export default function ProjectsPage() {
  const t = useTranslations();
  const me = useMe();
  const { data, error } = useApi<Project[]>("/projects");
  const { data: companies } = useApi<Company[]>("/companies");
  const { data: departments } = useApi<Department[]>("/departments");
  const [open, setOpen] = useState(false);

  const companyName = (id: string) => companies?.find((c) => c.id === id)?.name ?? "";

  return (
    <>
      <PageHeader
        title={t("projects.title")}
        description={t("projects.description")}
        actions={
          !me.is_partner && (
            <Button onClick={() => setOpen(true)}>
              <PlusIcon /> {t("projects.new")}
            </Button>
          )
        }
      />
      <ErrorText>{error}</ErrorText>
      {data &&
        (data.length === 0 ? (
          <Empty>{t("projects.empty")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("projects.name")}</TableHead>
                <TableHead>{t("projects.companyDept")}</TableHead>
                <TableHead className="text-right">{t("projects.packages")}</TableHead>
                <TableHead>{t("projects.openVulns")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Link href={{ pathname: "/projects/detail/", query: { id: p.id } }} className="font-medium hover:underline">
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
                    <SeverityCountsInline counts={p.open_counts} empty={t("common.none")} />
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
  const t = useTranslations();
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
      router.push({ pathname: "/projects/detail/", query: { id: p.id } });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const depts = departments.filter((d) => d.company_id === companyId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("projects.createTitle")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit}>
          <FieldGroup>
            <LabeledField label={t("projects.name")} htmlFor="project-name">
              <Input id="project-name" required value={name} onChange={(e) => setName(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("projects.descriptionField")} htmlFor="project-description">
              <Textarea id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("projects.company")}>
              <OptionSelect
                value={companyId}
                onValueChange={(v) => {
                  setCompanyId(v);
                  setDepartmentId("");
                }}
                options={selectable.map((c) => ({ value: c.id, label: c.name }))}
              />
            </LabeledField>
            <LabeledField label={t("projects.department")} hint={t("projects.departmentHint")}>
              <OptionSelect
                value={departmentId}
                onValueChange={setDepartmentId}
                options={[
                  { value: "", label: t("common.noneOption") },
                  ...depts.map((d) => ({ value: d.id, label: departmentPath(departments, d.id) })),
                ]}
              />
            </LabeledField>
            <ErrorText>{error}</ErrorText>
            <DialogFooter>
              <Button type="submit" disabled={!companyId}>
                {t("common.create")}
              </Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}
