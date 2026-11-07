"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { KanbanIcon, PlusIcon, TableIcon, UsersIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/navigation";
import {
  api,
  dealAmount,
  DELIVERY_STATUSES,
  hasRole,
  projectTab,
  todayISO,
  yen,
  type Company,
  type Customer,
  type Department,
  type Project,
  type ProjectMethod,
  type ProjectStatus,
  type ProjectTab,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { departmentPath } from "@/lib/org";
import { cn } from "@/lib/utils";
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
  PageTabs,
  SeverityCountsInline,
} from "@/components/common";
import { useMe } from "@/components/app-shell";
import { NextAction, ProjectStatusBadge, shortDate, userLabel } from "@/components/sales/status";

const TABS: ProjectTab[] = ["sales", "active", "maintenance", "closed"];
// Pipeline columns per tab. The last column of each is where a card leaves
// the tab (受注 → 進行中, 運用・保守 → 保守).
const COLUMNS: Partial<Record<ProjectTab, ProjectStatus[]>> = {
  sales: ["inquiry", "proposal", "negotiation", "won"],
  active: ["won", "development", "maintenance"],
};

function ProjectsPage() {
  const t = useTranslations();
  const me = useMe();
  const params = useSearchParams();
  const { data, error, reload } = useApi<Project[]>("/projects");
  const { data: companies } = useApi<Company[]>("/companies");
  const { data: departments } = useApi<Department[]>("/departments");
  const [open, setOpen] = useState(params.get("new") === "1");
  const [tab, setTab] = useState<ProjectTab>(() => {
    const q = params.get("tab") as ProjectTab | null;
    if (q && TABS.includes(q)) return q;
    return me.can_sell ? "sales" : "active";
  });
  const [views, setViews] = useState<Partial<Record<ProjectTab, "table" | "pipeline">>>({});
  const [customer, setCustomer] = useState("");
  const [owner, setOwner] = useState("");

  const view = COLUMNS[tab] ? (views[tab] ?? (tab === "sales" ? "pipeline" : "table")) : "table";
  const all = data ?? [];
  const inTab = (p: Project, tb: ProjectTab) =>
    projectTab(p) === tb ||
    // Cards just won this month stay visible in the sales pipeline's last column.
    (tb === "sales" && view === "pipeline" && p.status === "won" && (p.ordered_on ?? "").slice(0, 7) === todayISO().slice(0, 7));
  const filtered = all.filter(
    (p) =>
      (!customer || p.customer?.id === customer) &&
      (!owner || p.sales_owner?.id === owner || p.manager?.id === owner),
  );
  const rows = filtered.filter((p) => inTab(p, tab));
  const customers = new Map(all.filter((p) => p.customer).map((p) => [p.customer!.id, p.customer!.name]));
  const companyName = (id: string) => companies?.find((c) => c.id === id)?.name ?? "";

  return (
    <>
      <PageHeader
        title={t("projects.title")}
        description={me.can_sell || me.can_manage_org ? t("projects.descriptionSales") : t("projects.description")}
        actions={
          <>
            {me.can_see_customers && (
              <Button variant="outline" nativeButton={false} render={<Link href="/customers/" />}>
                <UsersIcon /> {t("nav.customers")}
              </Button>
            )}
            {!me.is_partner && (
              <Button onClick={() => setOpen(true)}>
                <PlusIcon /> {t("projects.new")}
              </Button>
            )}
          </>
        }
      />
      <ErrorText>{error}</ErrorText>
      {data && (
        <>
          {!me.is_partner && (
            <PageTabs
              value={tab}
              onChange={setTab}
              tabs={TABS.map((tb) => ({
                value: tb,
                label: (
                  <span className="flex items-center gap-1.5">
                    {t(`projects.tabs.${tb}`)}
                    <span className="rounded bg-muted px-1.5 text-[11px] tabular-nums text-muted-foreground">
                      {all.filter((p) => projectTab(p) === tb).length}
                    </span>
                  </span>
                ),
              }))}
            />
          )}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {COLUMNS[tab] && (
              <div className="flex rounded-md border p-0.5">
                {(["table", "pipeline"] as const).map((v) => (
                  <Button
                    key={v}
                    size="sm"
                    variant={view === v ? "secondary" : "ghost"}
                    onClick={() => setViews({ ...views, [tab]: v })}
                  >
                    {v === "table" ? <TableIcon /> : <KanbanIcon />}
                    {t(`projects.view.${v}`)}
                  </Button>
                ))}
              </div>
            )}
            {customers.size > 0 && (
              <OptionSelect
                value={customer}
                onValueChange={setCustomer}
                options={[
                  { value: "", label: t("projects.filter.allCustomers") },
                  ...[...customers].map(([id, name]) => ({ value: id, label: name })),
                ]}
              />
            )}
            {!me.is_partner && (
              <OptionSelect
                value={owner}
                onValueChange={setOwner}
                options={[
                  { value: "", label: t("projects.filter.allOwners") },
                  { value: me.id, label: t("projects.filter.mine") },
                ]}
              />
            )}
          </div>
          {all.length === 0 ? (
            <Empty>{t("projects.empty")}</Empty>
          ) : view === "pipeline" ? (
            <Pipeline columns={COLUMNS[tab]!} projects={rows} onMoved={reload} />
          ) : rows.length === 0 ? (
            <Empty>{t("projects.emptyTab")}</Empty>
          ) : (
            <ProjectTable tab={me.is_partner ? "active" : tab} rows={rows} companyName={companyName} departments={departments} />
          )}
        </>
      )}
      {companies && departments && open && (
        <CreateProjectDialog
          onOpenChange={setOpen}
          companies={companies}
          departments={departments}
          initialCustomer={params.get("customer") ?? ""}
          deal={tab === "sales" && me.can_sell}
        />
      )}
    </>
  );
}

function ProjectLink({ p }: { p: Project }) {
  return (
    <Link href={{ pathname: "/projects/detail/", query: { id: p.id } }} className="font-medium hover:underline">
      {p.name}
    </Link>
  );
}

function ProjectTable({
  tab,
  rows,
  companyName,
  departments,
}: {
  tab: ProjectTab;
  rows: Project[];
  companyName: (id: string) => string;
  departments: Department[] | undefined;
}) {
  const t = useTranslations();
  const org = (p: Project) => (
    <div className="text-xs text-muted-foreground">
      {p.department_id && departments ? departmentPath(departments, p.department_id) : companyName(p.company_id)}
    </div>
  );
  const customer = (p: Project) => <span className="text-xs">{p.customer?.name ?? t("projects.internal")}</span>;

  if (tab === "sales" || tab === "closed") {
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("projects.name")}</TableHead>
            <TableHead>{t("projects.customer")}</TableHead>
            <TableHead>{t("projects.status")}</TableHead>
            <TableHead className="text-right">{t("projects.amount")}</TableHead>
            {tab === "sales" ? (
              <>
                <TableHead className="text-right">{t("projects.probability")}</TableHead>
                <TableHead>{t("projects.nextAction")}</TableHead>
                <TableHead>{t("projects.salesOwner")}</TableHead>
              </>
            ) : (
              <TableHead>{t("projects.lostReason")}</TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.id}>
              <TableCell>
                <ProjectLink p={p} />
                {org(p)}
              </TableCell>
              <TableCell>{customer(p)}</TableCell>
              <TableCell>
                <ProjectStatusBadge status={p.status} />
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {dealAmount(p) != null ? yen(dealAmount(p)) : <span className="text-muted-foreground">{t("projects.noEstimate")}</span>}
              </TableCell>
              {tab === "sales" ? (
                <>
                  <TableCell className="text-right tabular-nums">{p.probability != null ? `${p.probability}%` : "—"}</TableCell>
                  <TableCell>
                    <NextAction text={p.next_action} on={p.next_action_on} />
                  </TableCell>
                  <TableCell className="text-xs">{userLabel(p.sales_owner)}</TableCell>
                </>
              ) : (
                <TableCell className="max-w-xs truncate text-xs">{p.lost_reason ?? "—"}</TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("projects.name")}</TableHead>
          <TableHead>{t("projects.customer")}</TableHead>
          <TableHead>{t("projects.status")}</TableHead>
          {tab === "maintenance" ? (
            <TableHead className="text-right">{t("projects.monthly")}</TableHead>
          ) : (
            <>
              <TableHead>{t("projects.method")}</TableHead>
              <TableHead>{t("projects.manager")}</TableHead>
              <TableHead>{t("projects.period")}</TableHead>
            </>
          )}
          <TableHead className="text-right">{t("projects.packages")}</TableHead>
          <TableHead>{t("projects.openVulns")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((p) => (
          <TableRow key={p.id}>
            <TableCell>
              <ProjectLink p={p} />
              {org(p)}
            </TableCell>
            <TableCell>{customer(p)}</TableCell>
            <TableCell>
              <ProjectStatusBadge status={p.status} />
            </TableCell>
            {tab === "maintenance" ? (
              <TableCell className="text-right tabular-nums">
                {p.monthly_amount != null ? t("projects.perMonth", { amount: yen(p.monthly_amount) }) : "—"}
              </TableCell>
            ) : (
              <>
                <TableCell className="text-xs">{t(`labels.method.${p.method}`)}</TableCell>
                <TableCell className="text-xs">{userLabel(p.manager)}</TableCell>
                <TableCell className="text-xs tabular-nums">
                  {p.starts_on || p.ends_on ? `${shortDate(p.starts_on)} – ${shortDate(p.ends_on)}` : "—"}
                </TableCell>
              </>
            )}
            <TableCell className="text-right tabular-nums">{p.package_count}</TableCell>
            <TableCell>
              <SeverityCountsInline counts={p.open_counts} empty={t("common.none")} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Pipeline({ columns, projects, onMoved }: { columns: ProjectStatus[]; projects: Project[]; onMoved: () => void }) {
  const t = useTranslations();
  const [over, setOver] = useState<ProjectStatus | null>(null);

  async function move(id: string, status: ProjectStatus) {
    const p = projects.find((x) => x.id === id);
    if (!p || p.status === status) return;
    try {
      await api(`/projects/${id}`, { method: "PATCH", json: { status } });
      toast.success(t("projects.moved", { name: p.name, status: t(`labels.projectStatus.${status}`) }));
      onMoved();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <>
      <div className="grid gap-3 overflow-x-auto pb-2" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(15rem, 1fr))` }}>
        {columns.map((status) => {
          const cards = projects.filter((p) => p.status === status);
          const total = cards.reduce((sum, p) => sum + (dealAmount(p) ?? 0), 0);
          return (
            <div
              key={status}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(status);
              }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => {
                e.preventDefault();
                setOver(null);
                move(e.dataTransfer.getData("text/plain"), status);
              }}
              className={cn("flex min-h-40 flex-col gap-2 rounded-lg bg-muted/50 p-2", over === status && "ring-2 ring-primary/40")}
            >
              <div className="flex items-baseline justify-between px-1 text-xs">
                <span className="font-medium">
                  {t(`labels.projectStatus.${status}`)} <span className="text-muted-foreground">{cards.length}</span>
                </span>
                <span className="tabular-nums text-muted-foreground">{total ? yen(total) : t("projects.amountUnknown")}</span>
              </div>
              {cards.map((p) => (
                <PipelineCard key={p.id} p={p} />
              ))}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t("projects.pipelineHint")}</p>
    </>
  );
}

function PipelineCard({ p }: { p: Project }) {
  const t = useTranslations();
  const overdue = !!p.next_action_on && p.next_action_on < todayISO();
  const amount = dealAmount(p);
  return (
    <div
      draggable={p.can_sell}
      onDragStart={(e) => e.dataTransfer.setData("text/plain", p.id)}
      className={cn(
        "grid gap-1 rounded-md border bg-card p-2.5 text-sm shadow-xs",
        p.can_sell && "cursor-grab active:cursor-grabbing",
        overdue && "border-destructive/60 bg-destructive/5",
      )}
    >
      <div className="text-xs text-muted-foreground">{p.customer?.name ?? t("projects.internal")}</div>
      <ProjectLink p={p} />
      <div className="flex items-center justify-between text-xs">
        <span className="tabular-nums">{amount != null ? yen(amount) : t("projects.noEstimate")}</span>
        <span className="text-muted-foreground">
          {t("projects.probabilityShort", { value: p.probability != null ? `${p.probability}%` : "—" })}
        </span>
      </div>
      {(p.next_action || p.next_action_on) && (
        <div className="border-t pt-1">
          <NextAction text={p.next_action} on={p.next_action_on} />
          <span className="text-xs text-muted-foreground"> ・ {userLabel(p.sales_owner)}</span>
        </div>
      )}
    </div>
  );
}

function CreateProjectDialog({
  onOpenChange,
  companies,
  departments,
  initialCustomer,
  deal,
}: {
  onOpenChange: (v: boolean) => void;
  companies: Company[];
  departments: Department[];
  initialCustomer: string;
  deal: boolean;
}) {
  const t = useTranslations();
  const me = useMe();
  const router = useRouter();
  const selectable = companies.filter(
    (c) => c.type !== "partner" && (hasRole(me, "group_admin") || c.id === me.company_id),
  );
  const [companyId, setCompanyId] = useState(me.company_id ?? selectable[0]?.id ?? "");
  const [departmentId, setDepartmentId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<ProjectStatus>(deal || initialCustomer ? "inquiry" : "development");
  const [method, setMethod] = useState<ProjectMethod>("waterfall");
  const [customerId, setCustomerId] = useState(initialCustomer);
  const [expected, setExpected] = useState("");
  const [probability, setProbability] = useState("");
  const [error, setError] = useState<string | null>(null);
  const canSell = me.can_sell || hasRole(me, "group_admin");
  const { data: customers } = useApi<Customer[]>(me.can_see_customers && companyId ? `/customers?company_id=${companyId}` : null);
  const isDeal = !DELIVERY_STATUSES.includes(status);
  const statuses: ProjectStatus[] = canSell
    ? ["inquiry", "proposal", "negotiation", "won", "development", "maintenance"]
    : ["development", "maintenance"];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const p = await api<Project>("/projects", {
        method: "POST",
        json: {
          name,
          description: description || null,
          company_id: companyId,
          department_id: departmentId || null,
          status,
          method,
          ...(canSell
            ? {
                customer_id: customerId || null,
                ...(isDeal
                  ? {
                      expected_amount: expected ? Number(expected) : null,
                      probability: probability ? Number(probability) : null,
                      sales_owner_id: me.id,
                    }
                  : {}),
              }
            : {}),
        },
      });
      router.push({ pathname: "/projects/detail/", query: { id: p.id } });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const depts = departments.filter((d) => d.company_id === companyId);

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("projects.createTitle")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit}>
          <FieldGroup>
            <LabeledField label={t("projects.name")} htmlFor="project-name">
              <Input id="project-name" required value={name} onChange={(e) => setName(e.target.value)} />
            </LabeledField>
            <div className="grid gap-4 sm:grid-cols-2">
              <LabeledField label={t("projects.status")} hint={canSell ? undefined : t("projects.statusHintInternal")}>
                <OptionSelect
                  value={status}
                  onValueChange={(v) => setStatus(v as ProjectStatus)}
                  options={statuses.map((s) => ({ value: s, label: t(`labels.projectStatus.${s}`) }))}
                />
              </LabeledField>
              <LabeledField label={t("projects.method")}>
                <OptionSelect
                  value={method}
                  onValueChange={(v) => setMethod(v as ProjectMethod)}
                  options={(["waterfall", "scrum"] as const).map((m) => ({ value: m, label: t(`labels.method.${m}`) }))}
                />
              </LabeledField>
            </div>
            {canSell && customers && (
              <LabeledField label={t("projects.customer")}>
                <OptionSelect
                  value={customerId}
                  onValueChange={setCustomerId}
                  options={[
                    { value: "", label: t("projects.internal") },
                    ...customers.map((c) => ({ value: c.id, label: c.name })),
                  ]}
                />
              </LabeledField>
            )}
            {canSell && isDeal && (
              <div className="grid gap-4 sm:grid-cols-2">
                <LabeledField label={t("projects.expectedAmount")} htmlFor="project-expected">
                  <Input id="project-expected" type="number" min={0} step={10000} value={expected} onChange={(e) => setExpected(e.target.value)} />
                </LabeledField>
                <LabeledField label={t("projects.probability")} htmlFor="project-probability">
                  <Input
                    id="project-probability"
                    type="number"
                    min={0}
                    max={100}
                    step={10}
                    value={probability}
                    onChange={(e) => setProbability(e.target.value)}
                  />
                </LabeledField>
              </div>
            )}
            <LabeledField label={t("projects.descriptionField")} htmlFor="project-description">
              <Textarea id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} />
            </LabeledField>
            <div className="grid gap-4 sm:grid-cols-2">
              <LabeledField label={t("projects.company")}>
                <OptionSelect
                  value={companyId}
                  onValueChange={(v) => {
                    setCompanyId(v);
                    setDepartmentId("");
                    setCustomerId("");
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
            </div>
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

export default function ProjectsPageWrapper() {
  return (
    <Suspense>
      <ProjectsPage />
    </Suspense>
  );
}
