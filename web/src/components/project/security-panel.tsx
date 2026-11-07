"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import {
  api,
  SEVERITIES,
  type Project,
  type SecurityCandidate,
  type Severity,
  type Task,
  type TaskDetail,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, OptionSelect, SeverityBadge } from "@/components/common";
import { EolBadge } from "@/components/eol-table";
import { UpgradeHint } from "@/components/upgrade-hint";
import { shortDate } from "@/components/sales/status";
import { DueLabel, Initials, TaskDialog, TaskStatusBadge, useTaskTitle } from "@/components/task/task-common";

type Filter = "open" | "all" | "done";
type Source = "all" | "vuln" | "eol";

/** Security tasks of a project: one per package (or runtime) upgrade, plus what is not a task yet. */
export function SecurityPanel({
  project,
  canWrite,
  canManage,
  onChanged,
}: {
  project: Project;
  canWrite: boolean;
  canManage: boolean;
  onChanged: () => void;
}) {
  const t = useTranslations();
  const { data: tasks, reload } = useApi<Task[]>(`/projects/${project.id}/tasks?kind=security`);
  const { data: candidates, reload: reloadCandidates } = useApi<SecurityCandidate[]>(
    `/projects/${project.id}/security/candidates`,
  );
  const [filter, setFilter] = useState<Filter>("open");
  const [source, setSource] = useState<Source>("all");
  const [detail, setDetail] = useState<Task | null>(null);
  const [editing, setEditing] = useState<Task | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const refresh = () => {
    reload();
    reloadCandidates();
    onChanged();
  };

  if (!tasks || !candidates) return null;
  const month = new Date().toISOString().slice(0, 7);
  const todo = tasks.filter((x) => x.status === "todo");
  const doing = tasks.filter((x) => x.status === "in_progress");
  const doneThisMonth = tasks.filter((x) => x.status === "done" && x.completed_at?.startsWith(month));
  const visible = tasks.filter(
    (x) =>
      (filter === "all" || (filter === "done" ? x.status === "done" : x.status !== "done")) &&
      (source === "all" ||
        (source === "vuln" ? (x.security?.vuln_count ?? 0) > 0 : !!x.security?.eol_status)),
  );
  const keyOf = (c: SecurityCandidate) => `${c.subject}|${c.ecosystem}|${c.name}`;

  async function setThreshold(value: string) {
    try {
      await api(`/projects/${project.id}`, { method: "PATCH", json: { security_threshold: value } });
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function createTasks(list: SecurityCandidate[]) {
    try {
      for (const c of list) {
        await api(`/projects/${project.id}/security/tasks`, {
          method: "POST",
          json: { subject: c.subject, ecosystem: c.ecosystem, name: c.name },
        });
      }
      toast.success(t("security.created"));
      setSelected(new Set());
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
        <div className="grid gap-0.5">
          <span className="text-sm font-medium">{t("security.threshold")}</span>
          <span className="text-xs text-muted-foreground">{t("security.thresholdHint")}</span>
        </div>
        <OptionSelect
          className="ml-auto"
          value={project.security_threshold}
          disabled={!canManage}
          onValueChange={setThreshold}
          options={SEVERITIES.filter((s) => s !== "UNKNOWN").map((s) => ({
            value: s,
            label: t("security.thresholdLabel", { severity: s }),
          }))}
        />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("security.todo")} value={todo.length} danger={todo.some((x) => x.overdue)} />
        <Stat label={t("security.inProgress")} value={doing.length} />
        <Stat label={t("security.doneThisMonth")} value={doneThisMonth.length} />
        <Stat label={t("security.candidates")} value={candidates.length} />
      </div>

      <section className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">{t("security.tasks")}</h3>
          <span className="text-xs text-muted-foreground">{t("security.tasksHint")}</span>
          <div className="ml-auto flex flex-wrap gap-2">
            <OptionSelect
              value={filter}
              onValueChange={(v) => setFilter(v as Filter)}
              options={(["open", "all", "done"] as const).map((f) => ({ value: f, label: t(`security.filter.${f}`) }))}
            />
            <OptionSelect
              value={source}
              onValueChange={(v) => setSource(v as Source)}
              options={(["all", "vuln", "eol"] as const).map((f) => ({ value: f, label: t(`security.source.${f}`) }))}
            />
          </div>
        </div>
        {visible.length === 0 ? (
          <Empty>{t("security.noTasks")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("security.subject")}</TableHead>
                <TableHead>{t("security.versions")}</TableHead>
                <TableHead>{t("security.linked")}</TableHead>
                <TableHead>{t("security.origin")}</TableHead>
                <TableHead>{t("tasks.assignee")}</TableHead>
                <TableHead>{t("tasks.dueDate")}</TableHead>
                <TableHead>{t("tasks.status")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((task) => (
                <TableRow key={task.id} className="cursor-pointer" onClick={() => setDetail(task)}>
                  <TableCell>
                    <div className={cn("font-medium", task.status === "done" && "text-muted-foreground line-through")}>
                      {task.title}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {task.security?.subject === "runtime" ? t("security.runtime") : task.security?.ecosystem} ・ #{task.number}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Versions task={task} />
                  </TableCell>
                  <TableCell>
                    <Linked task={task} />
                  </TableCell>
                  <TableCell className="text-xs">{task.auto_created ? t("tasks.auto") : t("tasks.manual")}</TableCell>
                  <TableCell>
                    <Initials user={task.assignee} />
                  </TableCell>
                  <TableCell>
                    <DueLabel task={task} />
                  </TableCell>
                  <TableCell>
                    <TaskStatusBadge status={task.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <section className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">{t("security.candidatesTitle")}</h3>
          <span className="text-xs text-muted-foreground">{t("security.candidatesHint")}</span>
          {canWrite && selected.size > 0 && (
            <Button
              className="ml-auto"
              size="sm"
              onClick={() => createTasks(candidates.filter((c) => selected.has(keyOf(c))))}
            >
              {t("security.createSelected")}
            </Button>
          )}
        </div>
        {candidates.length === 0 ? (
          <Empty>{t("security.noCandidates")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {canWrite && <TableHead className="w-8" />}
                <TableHead>{t("security.subject")}</TableHead>
                <TableHead>{t("security.linked")}</TableHead>
                <TableHead>{t("security.versions")}</TableHead>
                {canWrite && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {candidates.map((c) => (
                <TableRow key={keyOf(c)}>
                  {canWrite && (
                    <TableCell>
                      <Checkbox
                        checked={selected.has(keyOf(c))}
                        onCheckedChange={(v) => {
                          const next = new Set(selected);
                          if (v) next.add(keyOf(c));
                          else next.delete(keyOf(c));
                          setSelected(next);
                        }}
                        aria-label={c.label}
                      />
                    </TableCell>
                  )}
                  <TableCell>
                    <div className="font-medium">{c.label}</div>
                    <div className="text-xs text-muted-foreground">
                      {c.subject === "runtime" ? t("security.runtime") : c.ecosystem}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="flex flex-wrap items-center gap-1.5">
                      {c.max_severity && <SeverityBadge severity={c.max_severity as Severity} />}
                      {c.vuln_count > 0 && (
                        <span className="text-xs text-muted-foreground">{t("security.vulnCount", { count: c.vuln_count })}</span>
                      )}
                      {c.eol_status && <EolBadge status={c.eol_status} />}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">{c.installed.join(", ")}</span> <UpgradeHint upgrade={c.upgrade} />
                  </TableCell>
                  {canWrite && (
                    <TableCell className="text-right">
                      <Button size="sm" variant="outline" onClick={() => createTasks([c])}>
                        {t("security.createTask")}
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      {detail && (
        <SecurityTaskDialog
          task={detail}
          canWrite={canWrite}
          onClose={() => setDetail(null)}
          onEdit={() => {
            setEditing(detail);
            setDetail(null);
          }}
          onChanged={() => {
            setDetail(null);
            refresh();
          }}
        />
      )}
      {editing && (
        <TaskDialog
          projectId={project.id}
          task={editing}
          canWrite={canWrite}
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

function Stat({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  return (
    <Card className="gap-1 py-4">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={cn("text-2xl tabular-nums", danger && "text-red-600 dark:text-red-400")}>{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

function Versions({ task }: { task: Task }) {
  const s = task.security;
  if (!s) return null;
  return (
    <span className="flex flex-wrap items-center gap-1">
      <span className="font-mono text-xs">{s.installed.join(", ") || "—"}</span>
      {s.upgrade ? (
        <UpgradeHint upgrade={s.upgrade} />
      ) : (
        s.latest && <span className="font-mono text-xs text-muted-foreground">(latest {s.latest})</span>
      )}
    </span>
  );
}

function Linked({ task }: { task: Task }) {
  const t = useTranslations("security");
  const s = task.security;
  if (!s) return null;
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {s.max_severity && <SeverityBadge severity={s.max_severity} />}
      {s.vuln_count > 0 && <span className="text-xs text-muted-foreground">{t("vulnCount", { count: s.vuln_count })}</span>}
      {s.eol_status && <EolBadge status={s.eol_status} />}
      {s.eol_date && (
        <span className="text-xs text-muted-foreground">
          {t(s.eol_status === "eol" ? "eolEnded" : "eolApproaching", { date: shortDate(s.eol_date) })}
        </span>
      )}
    </span>
  );
}

function SecurityTaskDialog({
  task,
  canWrite,
  onClose,
  onEdit,
  onChanged,
}: {
  task: Task;
  canWrite: boolean;
  onClose: () => void;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const t = useTranslations();
  const titleOf = useTaskTitle();
  const { data } = useApi<TaskDetail>(`/tasks/${task.id}`);
  const upgrade = task.security?.upgrade;

  async function markDone() {
    try {
      await api(`/tasks/${task.id}`, { method: "PATCH", json: { status: "done" } });
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            #{task.number} {titleOf(task)}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <TaskStatusBadge status={task.status} />
          <Initials user={task.assignee} />
          <span className="text-muted-foreground">
            {t("tasks.dueDate")}: <DueLabel task={task} />
          </span>
        </div>
        {data && data.matches.length > 0 && (
          <div className="grid gap-2">
            <h4 className="text-sm font-semibold">{t("security.linkedVulns")}</h4>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>{t("matches.severity")}</TableHead>
                  <TableHead>{t("tasks.description")}</TableHead>
                  <TableHead>{t("security.fixedIn")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.matches.map((m) => (
                  <TableRow key={m.id} className={cn(m.status === "ignored" && "opacity-50")}>
                    <TableCell className="font-mono text-xs">{m.vuln_id}</TableCell>
                    <TableCell>
                      <SeverityBadge severity={m.severity} />
                    </TableCell>
                    <TableCell className="max-w-72 truncate text-xs" title={m.summary ?? ""}>
                      {m.summary ?? "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{m.fixed_version ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {upgrade?.version && upgrade.unfixed === 0 && (
              <p className="text-xs text-muted-foreground">{t("security.allFixed", { version: upgrade.version })}</p>
            )}
          </div>
        )}
        {data && data.findings.length > 0 && (
          <div className="grid gap-2">
            <h4 className="text-sm font-semibold">{t("security.linkedEol")}</h4>
            {data.findings.map((f) => (
              <div key={f.id} className="flex flex-wrap items-center gap-2 text-sm">
                <EolBadge status={f.status} />
                <span>
                  {f.product_label} {f.version}
                </span>
                {f.eol_date && <span className="text-xs text-muted-foreground">{shortDate(f.eol_date)}</span>}
              </div>
            ))}
          </div>
        )}
        {canWrite && (
          <DialogFooter className="sm:justify-between">
            <Button variant="outline" onClick={onEdit}>
              {t("tasks.editTitle")}
            </Button>
            {task.status !== "done" && <Button onClick={markDone}>{t("security.markDone")}</Button>}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
