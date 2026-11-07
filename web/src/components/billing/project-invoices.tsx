"use client";

import { useState } from "react";
import { PlusIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, todayISO, yen, type Estimate, type Invoice, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { OptionSelect } from "@/components/common";
import { shortDate } from "@/components/sales/status";
import { InvoiceStatusBadge, RecordActions } from "@/components/billing/invoice-common";

/** 請求予定 of the project, planned from its won estimates. */
export function ProjectInvoices({ project, estimates }: { project: Project; estimates: Estimate[] }) {
  const t = useTranslations("billing");
  const { data, reload } = useApi<Invoice[]>(`/projects/${project.id}/invoices`);
  const [planning, setPlanning] = useState<Estimate | null>(null);
  const won = estimates.filter((e) => e.status === "won");
  if (!won.length && !data?.length) return null;
  const unplanned = won.filter((e) => !(data ?? []).some((i) => i.estimate_id === e.id));

  return (
    <Card className="mt-2">
      <CardHeader>
        <CardTitle className="text-sm">{t("projectTitle")}</CardTitle>
        <CardDescription>{t("projectHint")}</CardDescription>
        {project.can_sell && won.length > 0 && (
          <CardAction>
            <OptionSelect
              value=""
              onValueChange={(id) => setPlanning(won.find((e) => e.id === id) ?? null)}
              options={[
                { value: "", label: t("plan") },
                ...won.map((e) => ({ value: e.id, label: e.title })),
              ]}
            />
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="grid gap-3">
        {unplanned.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            {t("unplanned", { titles: unplanned.map((e) => e.title).join("、") })}
          </p>
        )}
        {data && data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("plannedOn")}</TableHead>
                <TableHead>{t("item")}</TableHead>
                <TableHead className="text-right">{t("amount")}</TableHead>
                <TableHead>{t("statusLabel")}</TableHead>
                <TableHead>{t("progress")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((i) => (
                <TableRow key={i.id}>
                  <TableCell className="tabular-nums">{shortDate(i.planned_on)}</TableCell>
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
                  <TableCell className="text-xs text-muted-foreground tabular-nums">
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
        )}
      </CardContent>
      {planning && (
        <PlanDialog
          project={project}
          estimate={planning}
          invoices={(data ?? []).filter((i) => i.estimate_id === planning.id)}
          onClose={() => setPlanning(null)}
          onSaved={() => {
            setPlanning(null);
            reload();
          }}
        />
      )}
    </Card>
  );
}

type Item = { label: string; planned_on: string; amount: string };

function monthEnd(iso: string, plus = 0): string {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m + plus, 0)).toISOString().slice(0, 10);
}

function PlanDialog({
  project,
  estimate,
  invoices,
  onClose,
  onSaved,
}: {
  project: Project;
  estimate: Estimate;
  invoices: Invoice[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("billing");
  const tc = useTranslations("common");
  const monthly = estimate.billing === "monthly";
  const kept = invoices.filter((i) => i.status !== "planned");
  const planned = invoices.filter((i) => i.status === "planned");
  const total = estimate.amount ?? 0;
  const keptTotal = kept.reduce((s, i) => s + i.amount, 0);
  const end = project.ends_on ?? monthEnd(todayISO(), 1);

  const [items, setItems] = useState<Item[]>(() =>
    planned.length
      ? planned.map((i) => ({ label: i.label, planned_on: i.planned_on, amount: String(i.amount) }))
      : monthly
        ? []
        : [{ label: t("defaultLabel"), planned_on: monthEnd(end), amount: String(total - keptTotal) }],
  );
  const [from, setFrom] = useState(monthEnd(todayISO(), 1).slice(0, 7));
  const [months, setMonths] = useState("12");
  const [error, setError] = useState<string | null>(null);
  const sum = keptTotal + items.reduce((s, i) => s + (Number(i.amount) || 0), 0);
  const patch = (n: number, p: Partial<Item>) => setItems(items.map((it, j) => (j === n ? { ...it, ...p } : it)));

  /** Split the remaining amount by percentages, e.g. 30 / 70. */
  function split(percents: number[]) {
    const rest = total - keptTotal;
    const labels = percents.length === 2 ? [t("upfront"), t("onDelivery")] : percents.map((_, i) => t("installment", { n: i + 1 }));
    const start = project.starts_on ?? todayISO();
    const [sy, sm] = start.split("-").map(Number);
    const [ey, em] = end.split("-").map(Number);
    const span = Math.max(0, (ey - sy) * 12 + (em - sm));
    let left = rest;
    setItems(
      percents.map((p, i) => {
        const last = i === percents.length - 1;
        const amount = last ? left : Math.round((rest * p) / 100 / 1000) * 1000;
        left -= amount;
        const offset = percents.length === 1 ? span : Math.round((span * i) / (percents.length - 1));
        return { label: labels[i], planned_on: monthEnd(start, offset), amount: String(amount) };
      }),
    );
  }

  function generateMonths() {
    const n = Math.max(1, Math.min(120, Number(months) || 1));
    const out: Item[] = [];
    for (let i = 0; i < n; i++) {
      const on = monthEnd(`${from}-01`, i);
      const [y, m] = on.split("-").map(Number);
      out.push({ label: t("monthLabel", { year: y, month: m }), planned_on: on, amount: String(total) });
    }
    setItems(out);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/estimates/${estimate.id}/invoices`, {
        method: "PUT",
        json: {
          items: items
            .filter((i) => i.label.trim() && i.planned_on)
            .map((i) => ({ label: i.label, planned_on: i.planned_on, amount: Number(i.amount) || 0 })),
        },
      });
      toast.success(tc("saved"));
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("planTitle", { title: estimate.title })}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {monthly ? t("planMonthlyHint", { amount: yen(total) }) : t("planHint", { amount: yen(total) })}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {monthly ? (
            <>
              <Input type="month" aria-label={t("fromMonth")} className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
              <Input type="number" aria-label={t("months")} className="w-20" min={1} max={120} value={months} onChange={(e) => setMonths(e.target.value)} />
              <span className="text-sm text-muted-foreground">{t("monthsUnit")}</span>
              <Button type="button" variant="outline" size="sm" onClick={generateMonths}>
                {t("generate")}
              </Button>
            </>
          ) : (
            <>
              <span className="text-xs text-muted-foreground">{t("presets")}</span>
              {[[100], [30, 70], [50, 50], [30, 40, 30]].map((p) => (
                <Button key={p.join("-")} type="button" variant="outline" size="sm" onClick={() => split(p)}>
                  {p.join(" / ")}
                </Button>
              ))}
            </>
          )}
        </div>
        <form onSubmit={save} className="grid gap-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("item")}</TableHead>
                <TableHead className="w-40">{t("plannedOn")}</TableHead>
                <TableHead className="w-36 text-right">{t("amount")}</TableHead>
                <TableHead className="w-14 text-right">%</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {kept.map((i) => (
                <TableRow key={i.id} className="text-muted-foreground">
                  <TableCell>
                    {i.label} <InvoiceStatusBadge invoice={i} />
                  </TableCell>
                  <TableCell className="tabular-nums">{i.planned_on}</TableCell>
                  <TableCell className="text-right tabular-nums">{yen(i.amount)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{total ? Math.round((i.amount / total) * 100) : ""}</TableCell>
                  <TableCell />
                </TableRow>
              ))}
              {items.map((it, n) => (
                <TableRow key={n}>
                  <TableCell>
                    <Input required value={it.label} maxLength={200} onChange={(e) => patch(n, { label: e.target.value })} />
                  </TableCell>
                  <TableCell>
                    <Input type="date" required value={it.planned_on} onChange={(e) => patch(n, { planned_on: e.target.value })} />
                  </TableCell>
                  <TableCell>
                    <Input className="text-right" type="number" min={0} step={1000} value={it.amount} onChange={(e) => patch(n, { amount: e.target.value })} />
                  </TableCell>
                  <TableCell className="text-right text-xs tabular-nums">
                    {total && !monthly ? Math.round(((Number(it.amount) || 0) / total) * 100) : ""}
                  </TableCell>
                  <TableCell>
                    <Button type="button" variant="ghost" size="icon" aria-label={tc("delete")} onClick={() => setItems(items.filter((_, j) => j !== n))}>
                      <Trash2Icon />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setItems([...items, { label: "", planned_on: items.at(-1)?.planned_on ?? monthEnd(todayISO()), amount: "" }])
              }
            >
              <PlusIcon /> {t("addItem")}
            </Button>
            {!monthly && (
              <span className={sum === total ? "text-sm text-muted-foreground" : "text-sm text-amber-700 dark:text-amber-400"}>
                {t("sum", { sum: yen(sum), total: yen(total) })}
              </span>
            )}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {tc("cancel")}
            </Button>
            <Button type="submit">{tc("save")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
