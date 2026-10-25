"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { EOL_STATUSES, type EolFinding } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Input } from "@/components/ui/input";
import { Empty, ErrorText, OptionSelect, PageHeader } from "@/components/common";
import { EolTable } from "@/components/eol-table";

export default function EolPage() {
  const t = useTranslations("eol");
  const [status, setStatus] = useState("attention");
  const [q, setQ] = useState("");
  const query =
    status === "attention" ? "status=eol&status=approaching" : status ? `status=${status}` : "";
  const { data, error } = useApi<EolFinding[]>(`/eol?${query}`);

  const needle = q.trim().toLowerCase();
  const rows = (data ?? []).filter(
    (f) => !needle || [f.project_name, f.product, f.product_label, f.version].some((s) => s.toLowerCase().includes(needle)),
  );

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <>
            <Input className="w-48" placeholder={t("product")} value={q} onChange={(e) => setQ(e.target.value)} />
            <OptionSelect
              value={status}
              onValueChange={setStatus}
              options={[
                { value: "attention", label: t("attention") },
                { value: "", label: t("allStatuses") },
                ...EOL_STATUSES.map((s) => ({ value: s, label: t(`statusLabel.${s}`) })),
              ]}
            />
          </>
        }
      />
      <ErrorText>{error}</ErrorText>
      {data && (rows.length === 0 ? <Empty>{t("empty")}</Empty> : <EolTable findings={rows} showProject />)}
    </>
  );
}
