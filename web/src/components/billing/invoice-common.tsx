"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, todayISO, type Invoice } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { LabeledField } from "@/components/common";

export type InvoiceState = Invoice["status"] | "overdue";

export const invoiceState = (i: Pick<Invoice, "status" | "overdue">): InvoiceState => (i.overdue ? "overdue" : i.status);

const STYLE: Record<InvoiceState, string> = {
  planned: "bg-muted text-muted-foreground",
  invoiced: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
  paid: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  overdue: "bg-red-500/15 text-red-700 dark:text-red-300",
};

export function InvoiceStatusBadge({ invoice }: { invoice: Pick<Invoice, "status" | "overdue"> }) {
  const t = useTranslations("billing.status");
  const s = invoiceState(invoice);
  return (
    <span className={cn("inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap", STYLE[s])}>{t(s)}</span>
  );
}

/** 請求済にする / 入金済にする (with the date), or undo, for accounting and admins. */
export function RecordActions({ invoice, onChanged }: { invoice: Invoice; onChanged: () => void }) {
  const t = useTranslations("billing");
  const [step, setStep] = useState<"invoiced" | "paid" | null>(null);
  if (!invoice.can_record) return null;

  async function undo() {
    const to = invoice.status === "paid" ? "invoiced" : "planned";
    if (!confirm(t(to === "planned" ? "confirmUndoInvoiced" : "confirmUndoPaid"))) return;
    try {
      await api(`/invoices/${invoice.id}`, { method: "PATCH", json: { status: to } });
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="flex justify-end gap-1">
      {invoice.status === "planned" && (
        <Button size="sm" variant="outline" onClick={() => setStep("invoiced")}>
          {t("markInvoiced")}
        </Button>
      )}
      {invoice.status === "invoiced" && (
        <Button size="sm" variant={invoice.overdue ? "default" : "outline"} onClick={() => setStep("paid")}>
          {t("markPaid")}
        </Button>
      )}
      {invoice.status !== "planned" && (
        <Button size="sm" variant="ghost" onClick={undo}>
          {t("undo")}
        </Button>
      )}
      {step && <RecordDialog invoice={invoice} step={step} onClose={() => setStep(null)} onSaved={onChanged} />}
    </div>
  );
}

function endOfNextMonth(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m + 1, 0)).toISOString().slice(0, 10);
}

function RecordDialog({
  invoice,
  step,
  onClose,
  onSaved,
}: {
  invoice: Invoice;
  step: "invoiced" | "paid";
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations("billing");
  const tc = useTranslations("common");
  const today = todayISO();
  const [date, setDate] = useState(today);
  const [due, setDue] = useState(endOfNextMonth(today));
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/invoices/${invoice.id}`, {
        method: "PATCH",
        json: step === "invoiced" ? { status: "invoiced", invoiced_on: date, due_on: due } : { status: "paid", paid_on: date },
      });
      toast.success(t(step === "invoiced" ? "recordedInvoiced" : "recordedPaid"));
      onClose();
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t(step === "invoiced" ? "markInvoiced" : "markPaid")}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {invoice.project_name} ・ {invoice.label}
        </p>
        <form onSubmit={save}>
          <FieldGroup>
            <LabeledField label={t(step === "invoiced" ? "invoicedOn" : "paidOn")} htmlFor="inv-date">
              <Input
                id="inv-date"
                type="date"
                required
                value={date}
                onChange={(e) => {
                  setDate(e.target.value);
                  if (step === "invoiced" && e.target.value) setDue(endOfNextMonth(e.target.value));
                }}
              />
            </LabeledField>
            {step === "invoiced" && (
              <LabeledField label={t("dueOn")} htmlFor="inv-due" hint={t("dueHint")}>
                <Input id="inv-due" type="date" required value={due} onChange={(e) => setDue(e.target.value)} />
              </LabeledField>
            )}
          </FieldGroup>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
          <DialogFooter className="mt-4">
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
