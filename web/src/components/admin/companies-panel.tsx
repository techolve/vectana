"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, type Company, type CompanyType } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { OptionSelect } from "@/components/common";
import { useMe } from "@/components/app-shell";

const TYPES: CompanyType[] = ["parent", "affiliate", "partner"];

export function CompaniesPanel({ companies, onChanged }: { companies: Company[]; onChanged: () => void }) {
  const t = useTranslations();
  const me = useMe();
  const editable = me.role === "group_admin";
  const [name, setName] = useState("");
  const [type, setType] = useState<string>("affiliate");
  const typeOptions = TYPES.map((v) => ({ value: v, label: t(`labels.companyType.${v}`) }));

  async function call(fn: () => Promise<unknown>, ok?: string) {
    try {
      await fn();
      if (ok) toast.success(ok);
      onChanged();
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    }
  }

  return (
    <div className="grid gap-4">
      {editable && (
        <form
          className="flex flex-wrap items-end gap-2 rounded-xl border p-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await call(() => api("/companies", { method: "POST", json: { name, type } }), t("companies.added"))) setName("");
          }}
        >
          <div className="w-full text-sm font-medium">{t("companies.add")}</div>
          <Input className="max-w-xs" required placeholder={t("companies.name")} value={name} onChange={(e) => setName(e.target.value)} />
          <OptionSelect value={type} onValueChange={setType} options={typeOptions} />
          <Button type="submit">{t("common.add")}</Button>
        </form>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("companies.name")}</TableHead>
            <TableHead>{t("companies.type")}</TableHead>
            {editable && <TableHead />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {companies.map((c) => (
            <TableRow key={c.id}>
              <TableCell className="font-medium">{c.name}</TableCell>
              <TableCell>
                {editable ? (
                  <OptionSelect
                    value={c.type}
                    onValueChange={(v) => call(() => api(`/companies/${c.id}`, { method: "PATCH", json: { name: c.name, type: v } }))}
                    options={typeOptions}
                  />
                ) : (
                  t(`labels.companyType.${c.type}`)
                )}
              </TableCell>
              {editable && (
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const next = prompt(t("companies.newName"), c.name);
                      if (next && next !== c.name)
                        call(() => api(`/companies/${c.id}`, { method: "PATCH", json: { name: next, type: c.type } }));
                    }}
                  >
                    {t("common.rename")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() =>
                      confirm(t("companies.confirmDelete", { name: c.name })) &&
                      call(() => api(`/companies/${c.id}`, { method: "DELETE" }))
                    }
                  >
                    {t("common.delete")}
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
