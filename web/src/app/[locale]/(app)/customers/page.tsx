"use client";

import { useState } from "react";
import { PlusIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/navigation";
import { api, hasRole, yen, type Company, type Customer, type CustomerDetail } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorText, LabeledField, OptionSelect, PageHeader } from "@/components/common";
import { useMe } from "@/components/app-shell";
import { userLabel } from "@/components/sales/status";

export default function CustomersPage() {
  const t = useTranslations();
  const me = useMe();
  const [q, setQ] = useState("");
  const { data, error } = useApi<Customer[]>(me.can_see_customers ? "/customers" : null);
  const { data: companies } = useApi<Company[]>("/companies");
  const [open, setOpen] = useState(false);
  const multiCompany = new Set((data ?? []).map((c) => c.company_id)).size > 1;
  const needle = q.toLowerCase();
  const rows = (data ?? []).filter((c) => !needle || c.name.toLowerCase().includes(needle));

  if (!me.can_see_customers) return <ErrorText>{t("customers.notAllowed")}</ErrorText>;

  return (
    <>
      <PageHeader
        title={t("customers.title")}
        description={t("customers.description")}
        actions={
          me.can_sell && (
            <Button onClick={() => setOpen(true)}>
              <PlusIcon /> {t("customers.add")}
            </Button>
          )
        }
      />
      <ErrorText>{error}</ErrorText>
      <div className="mb-3">
        <Input className="max-w-xs" placeholder={t("customers.filter")} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {data &&
        (data.length === 0 ? (
          <Empty>{t("customers.empty")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("customers.name")}</TableHead>
                {multiCompany && <TableHead>{t("customers.company")}</TableHead>}
                <TableHead>{t("customers.primaryContact")}</TableHead>
                <TableHead>{t("customers.salesOwner")}</TableHead>
                <TableHead className="text-right">{t("customers.projects")}</TableHead>
                <TableHead className="text-right">{t("customers.pipeline")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <Link href={{ pathname: "/customers/detail/", query: { id: c.id } }} className="font-medium hover:underline">
                      {c.name}
                    </Link>
                    {c.industry && <div className="text-xs text-muted-foreground">{c.industry}</div>}
                  </TableCell>
                  {multiCompany && (
                    <TableCell className="text-xs">{companies?.find((x) => x.id === c.company_id)?.name}</TableCell>
                  )}
                  <TableCell className="text-xs">{c.primary_contact ?? "—"}</TableCell>
                  <TableCell className="text-xs">{userLabel(c.sales_owner)}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.project_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.pipeline_amount ? yen(c.pipeline_amount) : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      {data && data.length > 0 && <p className="mt-2 text-xs text-muted-foreground">{t("customers.pipelineHint")}</p>}
      {open && companies && <CreateCustomerDialog companies={companies} onClose={() => setOpen(false)} />}
    </>
  );
}

function CreateCustomerDialog({ companies, onClose }: { companies: Company[]; onClose: () => void }) {
  const t = useTranslations();
  const me = useMe();
  const router = useRouter();
  const selectable = companies.filter((c) => c.type !== "partner" && (hasRole(me, "group_admin") || c.id === me.company_id));
  const [companyId, setCompanyId] = useState(me.company_id ?? selectable[0]?.id ?? "");
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const c = await api<CustomerDetail>("/customers", {
        method: "POST",
        json: { name, industry: industry || null, company_id: companyId, sales_owner_id: me.id },
      });
      router.push({ pathname: "/customers/detail/", query: { id: c.id } });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("customers.add")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit}>
          <FieldGroup>
            <LabeledField label={t("customers.name")} htmlFor="customer-name">
              <Input id="customer-name" required value={name} onChange={(e) => setName(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("customers.industry")} htmlFor="customer-industry">
              <Input id="customer-industry" value={industry} onChange={(e) => setIndustry(e.target.value)} />
            </LabeledField>
            {selectable.length > 1 && (
              <LabeledField label={t("customers.company")} hint={t("customers.companyHint")}>
                <OptionSelect value={companyId} onValueChange={setCompanyId} options={selectable.map((c) => ({ value: c.id, label: c.name }))} />
              </LabeledField>
            )}
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
