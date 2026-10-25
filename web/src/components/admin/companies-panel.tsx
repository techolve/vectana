"use client";

import { useState } from "react";
import { toast } from "sonner";

import { api, COMPANY_TYPE_LABEL, type Company, type CompanyType } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select } from "@/components/common";
import { useMe } from "@/components/app-shell";

export function CompaniesPanel({ companies, onChanged }: { companies: Company[]; onChanged: () => void }) {
  const me = useMe();
  const editable = me.role === "group_admin";
  const [name, setName] = useState("");
  const [type, setType] = useState<CompanyType>("affiliate");

  async function call(fn: () => Promise<unknown>, ok?: string) {
    try {
      await fn();
      if (ok) toast.success(ok);
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="grid gap-4">
      {editable && (
        <form
          className="flex flex-wrap items-end gap-2 rounded-xl border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            call(() => api("/companies", { method: "POST", json: { name, type } }), "会社を追加しました").then(() =>
              setName(""),
            );
          }}
        >
          <div className="w-full text-sm font-medium">会社を追加</div>
          <Input className="max-w-xs" required placeholder="会社名" value={name} onChange={(e) => setName(e.target.value)} />
          <Select value={type} onChange={(e) => setType(e.target.value as CompanyType)}>
            {(Object.keys(COMPANY_TYPE_LABEL) as CompanyType[]).map((t) => (
              <option key={t} value={t}>
                {COMPANY_TYPE_LABEL[t]}
              </option>
            ))}
          </Select>
          <Button type="submit">追加</Button>
        </form>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>会社名</TableHead>
            <TableHead>種別</TableHead>
            {editable && <TableHead />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {companies.map((c) => (
            <TableRow key={c.id}>
              <TableCell className="font-medium">{c.name}</TableCell>
              <TableCell>
                {editable ? (
                  <Select
                    value={c.type}
                    onChange={(e) =>
                      call(() => api(`/companies/${c.id}`, { method: "PATCH", json: { name: c.name, type: e.target.value } }))
                    }
                  >
                    {(Object.keys(COMPANY_TYPE_LABEL) as CompanyType[]).map((t) => (
                      <option key={t} value={t}>
                        {COMPANY_TYPE_LABEL[t]}
                      </option>
                    ))}
                  </Select>
                ) : (
                  COMPANY_TYPE_LABEL[c.type]
                )}
              </TableCell>
              {editable && (
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const next = prompt("新しい会社名", c.name);
                      if (next && next !== c.name)
                        call(() => api(`/companies/${c.id}`, { method: "PATCH", json: { name: next, type: c.type } }));
                    }}
                  >
                    名前変更
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() => confirm(`${c.name} を削除しますか？`) && call(() => api(`/companies/${c.id}`, { method: "DELETE" }))}
                  >
                    削除
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
