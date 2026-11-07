"use client";

import { useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon, DownloadIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { apiDownload, todayISO, yen, type Company, type Invoice } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { useMe } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorText, OptionSelect, PageHeader } from "@/components/common";
import { shortDate } from "@/components/sales/status";
import { InvoiceStatusBadge, RecordActions, invoiceState, type InvoiceState } from "@/components/billing/invoice-common";

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return d.toISOString().slice(0, 7);
}

const FILTERS: ("" | InvoiceState)[] = ["", "planned", "invoiced", "overdue", "paid"];

/** 請求: the month's invoices for accounting and admins. */
export default function BillingPage() {
  const t = useTranslations("billing");
  const me = useMe();
  const [month, setMonth] = useState(() => todayISO().slice(0, 7));
  const [filter, setFilter] = useState<"" | InvoiceState>("");
  const [companyId, setCompanyId] = useState("");
  const { data: companies } = useApi<Company[]>("/companies");
  const params = `month=${month}${companyId ? `&company_id=${companyId}` : ""}`;
  const { data, error, reload } = useApi<Invoice[]>(me.can_see_invoices ? `/invoices?${params}` : null);

  if (!me.can_see_invoices) return <ErrorText>{t("notAllowed")}</ErrorText>;

  const all = data ?? [];
  const inMonth = (iso: string | null) => !!iso && iso.startsWith(month);
  const sum = (rows: Invoice[]) => rows.reduce((s, i) => s + i.amount, 0);
  const planned = all.filter((i) => inMonth(i.planned_on));
  const awaiting = all.filter((i) => i.status === "invoiced" && !i.overdue);
  const paid = all.filter((i) => i.status === "paid" && inMonth(i.paid_on));
  const overdue = all.filter((i) => i.overdue);
  const rows = filter ? all.filter((i) => invoiceState(i) === filter) : all;
  const ownCompanies = (companies ?? []).filter((c) => c.type !== "partner");
  const showCompany = me.roles.includes("group_admin") && ownCompanies.length > 1;

  const cards: { key: InvoiceState; label: string; rows: Invoice[]; tone?: string }[] = [
    { key: "planned", label: t("cards.planned"), rows: planned },
    { key: "invoiced", label: t("cards.awaiting"), rows: awaiting },
    { key: "paid", label: t("cards.paid"), rows: paid, tone: "text-emerald-700 dark:text-emerald-400" },
    { key: "overdue", label: t("cards.overdue"), rows: overdue, tone: overdue.length ? "text-destructive" : undefined },
  ];

  async function download() {
    try {
      const q = `${params}${filter ? `&status=${filter}` : ""}`;
      await apiDownload(`/invoices.csv?${q}`, `vectana-invoices-${month}.csv`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const [y, m] = month.split("-").map(Number);

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <Button variant="outline" onClick={download}>
            <DownloadIcon /> {t("csv")}
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex items-center">
          <Button variant="outline" size="icon" aria-label={t("prevMonth")} onClick={() => setMonth(shiftMonth(month, -1))}>
            <ChevronLeftIcon />
          </Button>
          <span className="min-w-28 px-3 text-center text-sm font-medium tabular-nums">{t("monthTitle", { year: y, month: m })}</span>
          <Button variant="outline" size="icon" aria-label={t("nextMonth")} onClick={() => setMonth(shiftMonth(month, 1))}>
            <ChevronRightIcon />
          </Button>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setMonth(todayISO().slice(0, 7))}>
          {t("thisMonth")}
        </Button>
        {showCompany && (
          <OptionSelect
            className="ml-auto"
            value={companyId}
            onValueChange={setCompanyId}
            options={[{ value: "", label: t("allCompanies") }, ...ownCompanies.map((c) => ({ value: c.id, label: c.name }))]}
          />
        )}
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => (
          <button
            key={c.key}
            type="button"
            className="text-left"
            onClick={() => setFilter(filter === c.key ? "" : c.key)}
            aria-pressed={filter === c.key}
          >
            <Card className={cn("transition-colors hover:bg-muted/40", filter === c.key && "ring-2 ring-primary")}>
              <CardHeader>
                <CardDescription>
                  {c.label} ・ {t("count", { count: c.rows.length })}
                </CardDescription>
                <CardTitle className={cn("text-2xl tabular-nums", c.tone)}>{yen(sum(c.rows))}</CardTitle>
              </CardHeader>
            </Card>
          </button>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <Button key={f || "all"} size="sm" variant={filter === f ? "secondary" : "ghost"} onClick={() => setFilter(f)}>
            {f ? t(`status.${f}`) : t("all")}
          </Button>
        ))}
      </div>
      <ErrorText>{error}</ErrorText>
      {data &&
        (rows.length === 0 ? (
          <Empty>{t("empty")}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("plannedOn")}</TableHead>
                  <TableHead>{t("project")}</TableHead>
                  <TableHead>{t("item")}</TableHead>
                  <TableHead className="text-right">{t("amount")}</TableHead>
                  <TableHead>{t("statusLabel")}</TableHead>
                  <TableHead>{t("progress")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((i) => (
                  <TableRow key={i.id} className={cn(i.overdue && "bg-red-500/5")}>
                    <TableCell className="tabular-nums">{shortDate(i.planned_on)}</TableCell>
                    <TableCell>
                      <Link href={{ pathname: "/projects/detail/", query: { id: i.project_id } }} className="font-medium hover:underline">
                        {i.project_name}
                      </Link>
                      {i.customer_name && <div className="text-xs text-muted-foreground">{i.customer_name}</div>}
                    </TableCell>
                    <TableCell>
                      <div>{i.label}</div>
                      <div className="text-xs text-muted-foreground">
                        {i.estimate_title} ({i.seq}/{i.count})
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{yen(i.amount)}</TableCell>
                    <TableCell>
                      <InvoiceStatusBadge invoice={i} />
                    </TableCell>
                    <TableCell className={cn("text-xs tabular-nums text-muted-foreground", i.overdue && "text-destructive")}>
                      {i.paid_on
                        ? t("paidOnShort", { date: shortDate(i.paid_on) })
                        : i.invoiced_on
                          ? t("invoicedOnShort", { date: shortDate(i.invoiced_on), due: shortDate(i.due_on) })
                          : ""}
                    </TableCell>
                    <TableCell>
                      <RecordActions invoice={i} onChanged={reload} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}
      <p className="mt-3 text-xs text-muted-foreground">{t("note")}</p>
    </>
  );
}
