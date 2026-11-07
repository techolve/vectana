"use client";

import { useState } from "react";
import { CheckIcon, PencilIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import {
  api,
  DELIVERY_STATUSES,
  yen,
  type Customer,
  type Project,
  type ProjectMethod,
  type ProjectStatus,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { LabeledField, OptionSelect } from "@/components/common";
import { useMe } from "@/components/app-shell";
import { NextAction, shortDate, userLabel } from "@/components/sales/status";
import { UserSelect } from "@/components/sales/user-select";

const STEPS: ProjectStatus[] = ["inquiry", "proposal", "negotiation", "won", "development", "maintenance"];

/** Where the project is between the first inquiry and maintenance. */
export function StatusStepper({ project }: { project: Project }) {
  const t = useTranslations("labels.projectStatus");
  if (!project.status) return null;
  const current = STEPS.indexOf(project.status);
  return (
    <div className="flex flex-wrap items-center gap-1 text-xs">
      {STEPS.map((s, i) => (
        <span
          key={s}
          className={cn(
            "flex items-center gap-1 rounded-full border px-2 py-0.5",
            i < current && "border-transparent bg-muted text-muted-foreground",
            i === current && "border-primary bg-primary text-primary-foreground",
            i > current && "text-muted-foreground",
          )}
        >
          {i < current && <CheckIcon className="size-3" />}
          {t(s)}
        </span>
      ))}
      {current < 0 && <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-700 dark:text-amber-300">{t(project.status)}</span>}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-2 py-1.5 text-sm">
      <div className="text-muted-foreground">{label}</div>
      <div>{children}</div>
    </div>
  );
}

export function OverviewPanel({
  project,
  canManage,
  onSaved,
}: {
  project: Project;
  canManage: boolean;
  onSaved: () => void;
}) {
  const t = useTranslations();
  const me = useMe();
  const [editing, setEditing] = useState(false);
  const canEdit = canManage || project.can_sell;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{t("overview.basics")}</CardTitle>
          {canEdit && (
            <CardAction>
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <PencilIcon /> {t("common.edit")}
              </Button>
            </CardAction>
          )}
        </CardHeader>
        <CardContent className="divide-y">
          {!me.is_partner && (
            <Row label={t("projects.customer")}>
              {project.customer ? (
                me.can_see_customers ? (
                  <Link href={{ pathname: "/customers/detail/", query: { id: project.customer.id } }} className="hover:underline">
                    {project.customer.name}
                  </Link>
                ) : (
                  project.customer.name
                )
              ) : (
                t("projects.internal")
              )}
            </Row>
          )}
          <Row label={t("projects.method")}>{t(`labels.method.${project.method}`)}</Row>
          <Row label={t("projects.manager")}>{userLabel(project.manager)}</Row>
          <Row label={t("projects.period")}>
            {project.starts_on || project.ends_on ? `${shortDate(project.starts_on)} – ${shortDate(project.ends_on)}` : "—"}
          </Row>
          {!me.is_partner && (
            <>
              <Row label={t("projects.salesOwner")}>{userLabel(project.sales_owner)}</Row>
              <Row label={t("overview.orderedOn")}>{shortDate(project.ordered_on)}</Row>
            </>
          )}
        </CardContent>
      </Card>
      {!me.is_partner && (
        <Card>
          <CardHeader>
            <CardTitle>{project.is_deal ? t("overview.deal") : t("overview.money")}</CardTitle>
          </CardHeader>
          <CardContent className="divide-y">
            {project.is_deal ? (
              <>
                <Row label={t("projects.expectedAmount")}>{yen(project.expected_amount)}</Row>
                <Row label={t("overview.openEstimates")}>
                  {project.estimate_count ? yen(project.open_estimate_amount) : t("projects.noEstimate")}
                </Row>
                <Row label={t("projects.probability")}>{project.probability != null ? `${project.probability}%` : "—"}</Row>
                <Row label={t("projects.nextAction")}>
                  <NextAction text={project.next_action} on={project.next_action_on} />
                </Row>
              </>
            ) : (
              <>
                <Row label={t("overview.wonAmount")}>{yen(project.won_amount)}</Row>
                <Row label={t("projects.monthly")}>
                  {project.monthly_amount != null ? t("projects.perMonth", { amount: yen(project.monthly_amount) }) : "—"}
                </Row>
                <Row label={t("overview.openEstimates")}>{project.open_estimate_amount ? yen(project.open_estimate_amount) : "—"}</Row>
              </>
            )}
            {project.status === "lost" && (
              <>
                <Row label={t("projects.lostReason")}>{project.lost_reason ?? "—"}</Row>
                <Row label={t("overview.competitor")}>{project.competitor ?? "—"}</Row>
              </>
            )}
          </CardContent>
        </Card>
      )}
      {editing && <EditProjectDialog project={project} canManage={canManage} onClose={() => setEditing(false)} onSaved={onSaved} />}
    </div>
  );
}

function EditProjectDialog({
  project,
  canManage,
  onClose,
  onSaved,
}: {
  project: Project;
  canManage: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations();
  const me = useMe();
  const selling = project.can_sell;
  const { data: customers } = useApi<Customer[]>(selling ? `/customers?company_id=${project.company_id}` : null);
  const [status, setStatus] = useState<ProjectStatus>(project.status ?? "development");
  const [method, setMethod] = useState<ProjectMethod>(project.method);
  const [customerId, setCustomerId] = useState(project.customer?.id ?? "");
  const [managerId, setManagerId] = useState(project.manager?.id ?? "");
  const [salesOwnerId, setSalesOwnerId] = useState(project.sales_owner?.id ?? "");
  const [startsOn, setStartsOn] = useState(project.starts_on ?? "");
  const [endsOn, setEndsOn] = useState(project.ends_on ?? "");
  const [expected, setExpected] = useState(project.expected_amount?.toString() ?? "");
  const [probability, setProbability] = useState(project.probability?.toString() ?? "");
  const [nextAction, setNextAction] = useState(project.next_action ?? "");
  const [nextActionOn, setNextActionOn] = useState(project.next_action_on ?? "");
  const [lostReason, setLostReason] = useState(project.lost_reason ?? "");
  const [competitor, setCompetitor] = useState(project.competitor ?? "");

  // Without sales rights, only moves between delivery statuses are allowed.
  const statuses: ProjectStatus[] = selling
    ? ["inquiry", "proposal", "negotiation", "won", "development", "maintenance", "on_hold", "lost"]
    : project.status && DELIVERY_STATUSES.includes(project.status)
      ? DELIVERY_STATUSES
      : [];

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = {};
    if (statuses.length && status !== project.status) body.status = status;
    if (canManage) {
      Object.assign(body, {
        method,
        manager_id: managerId || null,
        starts_on: startsOn || null,
        ends_on: endsOn || null,
      });
    }
    if (selling) {
      Object.assign(body, {
        customer_id: customerId || null,
        sales_owner_id: salesOwnerId || null,
        expected_amount: expected ? Number(expected) : null,
        probability: probability ? Number(probability) : null,
        next_action: nextAction || null,
        next_action_on: nextActionOn || null,
        lost_reason: lostReason || null,
        competitor: competitor || null,
      });
    }
    try {
      await api(`/projects/${project.id}`, { method: "PATCH", json: body });
      toast.success(t("common.saved"));
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("overview.editTitle")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-2">
              {statuses.length > 0 && (
                <LabeledField label={t("projects.status")}>
                  <OptionSelect
                    value={status}
                    onValueChange={(v) => setStatus(v as ProjectStatus)}
                    options={statuses.map((s) => ({ value: s, label: t(`labels.projectStatus.${s}`) }))}
                  />
                </LabeledField>
              )}
              {canManage && (
                <LabeledField label={t("projects.method")} hint={t("overview.methodHint")}>
                  <OptionSelect
                    value={method}
                    onValueChange={(v) => setMethod(v as ProjectMethod)}
                    options={(["waterfall", "scrum"] as const).map((m) => ({ value: m, label: t(`labels.method.${m}`) }))}
                  />
                </LabeledField>
              )}
            </div>
            {canManage && !me.is_partner && (
              <div className="grid gap-4 sm:grid-cols-3">
                <LabeledField label={t("projects.manager")}>
                  <UserSelect value={managerId} onChange={setManagerId} current={project.manager} />
                </LabeledField>
                <LabeledField label={t("overview.startsOn")} htmlFor="p-starts">
                  <Input id="p-starts" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
                </LabeledField>
                <LabeledField label={t("overview.endsOn")} htmlFor="p-ends">
                  <Input id="p-ends" type="date" value={endsOn} onChange={(e) => setEndsOn(e.target.value)} />
                </LabeledField>
              </div>
            )}
            {selling && (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <LabeledField label={t("projects.customer")}>
                    <OptionSelect
                      value={customerId}
                      onValueChange={setCustomerId}
                      options={[
                        { value: "", label: t("projects.internal") },
                        ...(customers ?? []).map((c) => ({ value: c.id, label: c.name })),
                      ]}
                    />
                  </LabeledField>
                  <LabeledField label={t("projects.salesOwner")}>
                    <UserSelect value={salesOwnerId} onChange={setSalesOwnerId} current={project.sales_owner} />
                  </LabeledField>
                  <LabeledField label={t("projects.expectedAmount")} htmlFor="p-expected">
                    <Input id="p-expected" type="number" min={0} step={10000} value={expected} onChange={(e) => setExpected(e.target.value)} />
                  </LabeledField>
                  <LabeledField label={t("projects.probability")} htmlFor="p-probability">
                    <Input
                      id="p-probability"
                      type="number"
                      min={0}
                      max={100}
                      step={10}
                      value={probability}
                      onChange={(e) => setProbability(e.target.value)}
                    />
                  </LabeledField>
                </div>
                <div className="grid gap-4 sm:grid-cols-[1fr_11rem]">
                  <LabeledField label={t("projects.nextAction")} htmlFor="p-next">
                    <Input id="p-next" value={nextAction} onChange={(e) => setNextAction(e.target.value)} />
                  </LabeledField>
                  <LabeledField label={t("overview.nextActionOn")} htmlFor="p-next-on">
                    <Input id="p-next-on" type="date" value={nextActionOn} onChange={(e) => setNextActionOn(e.target.value)} />
                  </LabeledField>
                </div>
                {(status === "lost" || project.status === "lost") && (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <LabeledField label={t("projects.lostReason")} htmlFor="p-lost">
                      <Textarea id="p-lost" value={lostReason} onChange={(e) => setLostReason(e.target.value)} />
                    </LabeledField>
                    <LabeledField label={t("overview.competitor")} htmlFor="p-competitor">
                      <Input id="p-competitor" value={competitor} onChange={(e) => setCompetitor(e.target.value)} />
                    </LabeledField>
                  </div>
                )}
              </>
            )}
            <DialogFooter>
              <Button type="submit">{t("common.save")}</Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}
