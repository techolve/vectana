"use client";

import { useState } from "react";
import { PlusIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import {
  api,
  ESTIMATE_KINDS,
  ESTIMATE_STATUSES,
  yen,
  type Estimate,
  type EstimateKind,
  type EstimateStatus,
  type Project,
  type UserBrief,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorText, LabeledField, OptionSelect } from "@/components/common";
import { EstimateStatusBadge, shortDate, userLabel } from "@/components/sales/status";

export function EstimatesPanel({ project, onChanged }: { project: Project; onChanged: () => void }) {
  const t = useTranslations();
  const { data, error, reload } = useApi<Estimate[]>(`/projects/${project.id}/estimates`);
  const [editing, setEditing] = useState<Estimate | "new" | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const showCost = (data ?? []).some((e) => e.cost != null || e.lines.some((l) => l.unit_cost != null));

  const refresh = () => {
    reload();
    onChanged();
  };

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">{t("estimates.description")}</p>
        {project.can_sell && (
          <Button onClick={() => setEditing("new")}>
            <PlusIcon /> {t("estimates.add")}
          </Button>
        )}
      </div>
      <ErrorText>{error}</ErrorText>
      {data &&
        (data.length === 0 ? (
          <Empty>{t("estimates.empty")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("estimates.title")}</TableHead>
                <TableHead>{t("estimates.kind")}</TableHead>
                <TableHead className="text-right">{t("estimates.amount")}</TableHead>
                <TableHead className="text-right">{t("estimates.effort")}</TableHead>
                <TableHead className="text-right">{t("estimates.margin")}</TableHead>
                {showCost && <TableHead className="text-right">{t("estimates.cost")}</TableHead>}
                <TableHead>{t("estimates.status")}</TableHead>
                <TableHead>{t("estimates.date")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => (
                <EstimateRows
                  key={e.id}
                  estimate={e}
                  showCost={showCost}
                  expanded={expanded === e.id}
                  onToggle={() => setExpanded(expanded === e.id ? null : e.id)}
                  onEdit={project.can_sell ? () => setEditing(e) : undefined}
                />
              ))}
            </TableBody>
          </Table>
        ))}
      {!showCost && data && data.length > 0 && <p className="text-xs text-muted-foreground">{t("estimates.costHidden")}</p>}
      {editing && (
        <EstimateDialog
          project={project}
          estimate={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function EstimateRows({
  estimate: e,
  showCost,
  expanded,
  onToggle,
  onEdit,
}: {
  estimate: Estimate;
  showCost: boolean;
  expanded: boolean;
  onToggle: () => void;
  onEdit?: () => void;
}) {
  const t = useTranslations();
  const amount =
    e.billing === "monthly" && e.amount != null ? t("projects.perMonth", { amount: yen(e.amount) }) : yen(e.amount);
  const note =
    e.status === "lost" && e.lost_reason
      ? t("estimates.reason", { reason: e.lost_reason })
      : e.due_on && e.status !== "won"
        ? t("estimates.dueOn", { date: shortDate(e.due_on) })
        : e.valid_until
          ? t("estimates.validUntil", { date: shortDate(e.valid_until) })
          : null;
  return (
    <>
      <TableRow className={e.lines.length ? "cursor-pointer" : undefined} onClick={e.lines.length ? onToggle : undefined}>
        <TableCell>
          <div className="font-medium">{e.title}</div>
          {note && <div className="text-xs text-muted-foreground">{note}</div>}
        </TableCell>
        <TableCell className="text-xs">{t(`labels.estimateKind.${e.kind}`)}</TableCell>
        <TableCell className="text-right tabular-nums">{amount}</TableCell>
        <TableCell className="text-right tabular-nums">
          {e.effort_days != null ? t("estimates.days", { days: e.effort_days }) : "—"}
        </TableCell>
        <TableCell className="text-right tabular-nums">{e.margin != null ? `${Math.round(e.margin * 100)}%` : "—"}</TableCell>
        {showCost && <TableCell className="text-right tabular-nums">{yen(e.cost)}</TableCell>}
        <TableCell>
          <EstimateStatusBadge status={e.status} />
        </TableCell>
        <TableCell className="text-xs tabular-nums">{shortDate(e.decided_on ?? e.issued_on ?? e.created_at)}</TableCell>
        <TableCell className="text-right">
          {onEdit && (
            <Button
              variant="outline"
              size="sm"
              onClick={(ev) => {
                ev.stopPropagation();
                onEdit();
              }}
            >
              {t("common.edit")}
            </Button>
          )}
        </TableCell>
      </TableRow>
      {expanded &&
        e.lines.map((l) => (
          <TableRow key={l.id} className="bg-muted/30 text-xs">
            <TableCell className="pl-8">
              {l.label}
              {l.user && <span className="ml-2 text-muted-foreground">{userLabel(l.user)}</span>}
            </TableCell>
            <TableCell />
            <TableCell className="text-right tabular-nums">
              {l.unit_cost != null ? t("estimates.perDay", { amount: yen(l.unit_cost) }) : null}
            </TableCell>
            <TableCell className="text-right tabular-nums">{t("estimates.days", { days: l.days })}</TableCell>
            <TableCell />
            {showCost && <TableCell className="text-right tabular-nums">{yen(l.cost)}</TableCell>}
            <TableCell colSpan={3} />
          </TableRow>
        ))}
    </>
  );
}

type LineDraft = { label: string; user_id: string; days: string; unit_cost: string };

function EstimateDialog({
  project,
  estimate,
  onClose,
  onSaved,
}: {
  project: Project;
  estimate: Estimate | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations();
  const { data: members } = useApi<{ user_id: string; email: string; display_name: string | null; company_id: string | null }[]>(
    `/projects/${project.id}/members`,
  );
  const [title, setTitle] = useState(estimate?.title ?? "");
  const [kind, setKind] = useState<EstimateKind>(estimate?.kind ?? (project.estimate_count ? "additional" : "initial"));
  const [status, setStatus] = useState<EstimateStatus>(estimate?.status ?? "draft");
  const [monthly, setMonthly] = useState(estimate?.billing === "monthly");
  const [amount, setAmount] = useState(estimate?.amount?.toString() ?? "");
  const [effort, setEffort] = useState(estimate?.effort_days?.toString() ?? "");
  const [issuedOn, setIssuedOn] = useState(estimate?.issued_on ?? "");
  const [dueOn, setDueOn] = useState(estimate?.due_on ?? "");
  const [validUntil, setValidUntil] = useState(estimate?.valid_until ?? "");
  const [lostReason, setLostReason] = useState(estimate?.lost_reason ?? "");
  const [competitor, setCompetitor] = useState(estimate?.competitor ?? "");
  const [notes, setNotes] = useState(estimate?.notes ?? "");
  const [lines, setLines] = useState<LineDraft[]>(
    (estimate?.lines ?? []).map((l) => ({
      label: l.label,
      user_id: l.user?.id ?? "",
      days: String(l.days),
      unit_cost: l.unit_cost?.toString() ?? "",
    })),
  );
  const [error, setError] = useState<string | null>(null);

  const people: UserBrief[] = (members ?? []).map((m) => ({
    id: m.user_id,
    email: m.email,
    display_name: m.display_name,
    company_id: m.company_id,
  }));
  for (const l of estimate?.lines ?? []) if (l.user && !people.some((p) => p.id === l.user!.id)) people.push(l.user);
  const totalDays = lines.reduce((s, l) => s + (Number(l.days) || 0), 0);
  const totalCost = lines.reduce((s, l) => s + (Number(l.days) || 0) * (Number(l.unit_cost) || 0), 0);
  const anyCost = lines.some((l) => l.unit_cost !== "");
  const margin = anyCost && Number(amount) ? (Number(amount) - totalCost) / Number(amount) : null;
  const patchLine = (i: number, p: Partial<LineDraft>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...p } : l)));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      title,
      kind,
      status,
      billing: monthly ? "monthly" : "one_time",
      amount: amount ? Number(amount) : null,
      effort_days: lines.length ? null : effort ? Number(effort) : null,
      issued_on: issuedOn || null,
      due_on: dueOn || null,
      valid_until: validUntil || null,
      lost_reason: lostReason || null,
      competitor: competitor || null,
      notes: notes || null,
      lines: lines
        .filter((l) => l.label.trim())
        .map((l) => ({
          label: l.label,
          user_id: l.user_id || null,
          days: Number(l.days) || 0,
          // Empty: the server copies the person's current unit cost.
          unit_cost: l.unit_cost === "" ? null : Number(l.unit_cost),
        })),
    };
    try {
      await api(estimate ? `/estimates/${estimate.id}` : `/projects/${project.id}/estimates`, {
        method: estimate ? "PATCH" : "POST",
        json: body,
      });
      toast.success(t("common.saved"));
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove() {
    if (!estimate || !confirm(t("estimates.confirmDelete", { title: estimate.title }))) return;
    try {
      await api(`/estimates/${estimate.id}`, { method: "DELETE" });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{estimate ? t("estimates.editTitle") : t("estimates.add")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <FieldGroup>
            <LabeledField label={t("estimates.title")} htmlFor="est-title">
              <Input id="est-title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("estimates.titlePlaceholder")} />
            </LabeledField>
            <div className="grid gap-4 sm:grid-cols-3">
              <LabeledField label={t("estimates.kind")}>
                <OptionSelect
                  value={kind}
                  onValueChange={(v) => {
                    setKind(v as EstimateKind);
                    if (v === "maintenance") setMonthly(true);
                  }}
                  options={ESTIMATE_KINDS.map((k) => ({ value: k, label: t(`labels.estimateKind.${k}`) }))}
                />
              </LabeledField>
              <LabeledField label={t("estimates.status")} hint={t("estimates.statusHint")}>
                <OptionSelect
                  value={status}
                  onValueChange={(v) => setStatus(v as EstimateStatus)}
                  options={ESTIMATE_STATUSES.map((s) => ({ value: s, label: t(`labels.estimateStatus.${s}`) }))}
                />
              </LabeledField>
              <LabeledField label={t("estimates.billing")}>
                <OptionSelect
                  value={monthly ? "monthly" : "one_time"}
                  onValueChange={(v) => setMonthly(v === "monthly")}
                  options={[
                    { value: "one_time", label: t("estimates.oneTime") },
                    { value: "monthly", label: t("estimates.monthly") },
                  ]}
                />
              </LabeledField>
            </div>
            <div className="grid gap-4 sm:grid-cols-4">
              <LabeledField label={monthly ? t("estimates.amountMonthly") : t("estimates.amount")} htmlFor="est-amount">
                <Input id="est-amount" type="number" min={0} step={10000} value={amount} onChange={(e) => setAmount(e.target.value)} />
              </LabeledField>
              <LabeledField label={t("estimates.issuedOn")} htmlFor="est-issued">
                <Input id="est-issued" type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} />
              </LabeledField>
              <LabeledField label={t("estimates.dueOnLabel")} htmlFor="est-due">
                <Input id="est-due" type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
              </LabeledField>
              <LabeledField label={t("estimates.validUntilLabel")} htmlFor="est-valid">
                <Input id="est-valid" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
              </LabeledField>
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{t("estimates.lines")}</span>
                <Button type="button" variant="outline" size="sm" onClick={() => setLines([...lines, { label: "", user_id: "", days: "", unit_cost: "" }])}>
                  <PlusIcon /> {t("estimates.addLine")}
                </Button>
              </div>
              {lines.length === 0 ? (
                <div className="flex items-end gap-3">
                  <LabeledField label={t("estimates.effortTotal")} htmlFor="est-effort" hint={t("estimates.effortHint")}>
                    <Input id="est-effort" className="w-32" type="number" min={0} step={0.5} value={effort} onChange={(e) => setEffort(e.target.value)} />
                  </LabeledField>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("estimates.lineLabel")}</TableHead>
                      <TableHead>{t("estimates.person")}</TableHead>
                      <TableHead className="w-24 text-right">{t("estimates.effort")}</TableHead>
                      <TableHead className="w-32 text-right">{t("estimates.unitCost")}</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {lines.map((l, i) => (
                      <TableRow key={i}>
                        <TableCell>
                          <Input value={l.label} onChange={(e) => patchLine(i, { label: e.target.value })} placeholder={t("estimates.linePlaceholder")} />
                        </TableCell>
                        <TableCell>
                          <OptionSelect
                            value={l.user_id}
                            onValueChange={(v) => patchLine(i, { user_id: v, unit_cost: "" })}
                            options={[{ value: "", label: t("common.noneOption") }, ...people.map((p) => ({ value: p.id, label: userLabel(p) }))]}
                          />
                        </TableCell>
                        <TableCell>
                          <Input className="text-right" type="number" min={0} step={0.5} value={l.days} onChange={(e) => patchLine(i, { days: e.target.value })} />
                        </TableCell>
                        <TableCell>
                          <Input
                            className="text-right"
                            type="number"
                            min={0}
                            step={1000}
                            value={l.unit_cost}
                            placeholder={l.user_id ? t("estimates.fromUser") : ""}
                            onChange={(e) => patchLine(i, { unit_cost: e.target.value })}
                          />
                        </TableCell>
                        <TableCell>
                          <Button type="button" variant="ghost" size="icon" onClick={() => setLines(lines.filter((_, j) => j !== i))}>
                            <Trash2Icon />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              {lines.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {t("estimates.summary", {
                    days: totalDays,
                    cost: anyCost ? yen(Math.round(totalCost)) : "—",
                    margin: margin != null ? `${Math.round(margin * 100)}%` : "—",
                  })}
                </p>
              )}
            </div>

            {status === "lost" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <LabeledField label={t("projects.lostReason")} htmlFor="est-lost">
                  <Textarea id="est-lost" value={lostReason} onChange={(e) => setLostReason(e.target.value)} />
                </LabeledField>
                <LabeledField label={t("overview.competitor")} htmlFor="est-competitor">
                  <Input id="est-competitor" value={competitor} onChange={(e) => setCompetitor(e.target.value)} />
                </LabeledField>
              </div>
            )}
            <LabeledField label={t("estimates.notes")} htmlFor="est-notes">
              <Textarea id="est-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </LabeledField>
            <ErrorText>{error}</ErrorText>
            <DialogFooter className="sm:justify-between">
              {estimate ? (
                <Button type="button" variant="ghost" className="text-destructive" onClick={remove}>
                  {t("common.delete")}
                </Button>
              ) : (
                <span />
              )}
              <Button type="submit">{t("common.save")}</Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}
