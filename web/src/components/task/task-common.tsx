"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import {
  api,
  TASK_KINDS,
  TASK_STATUSES,
  type Member,
  type Sprint,
  type Task,
  type TaskKind,
  type TaskStatus,
  type UserBrief,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, LabeledField, OptionSelect } from "@/components/common";
import { shortDate, userLabel } from "@/components/sales/status";

export const KIND_STYLE: Record<TaskKind, string> = {
  development: "bg-sky-500/15 text-sky-700 dark:text-sky-400",
  security: "bg-red-500/15 text-red-700 dark:text-red-400",
  other: "bg-muted text-muted-foreground",
};

export const STATUS_STYLE: Record<TaskStatus, string> = {
  todo: "bg-muted text-muted-foreground",
  in_progress: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  done: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
};

export function TaskKindBadge({ kind }: { kind: TaskKind }) {
  const t = useTranslations("labels.taskKind");
  return <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap", KIND_STYLE[kind])}>{t(kind)}</span>;
}

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const t = useTranslations("labels.taskStatus");
  return <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap", STATUS_STYLE[status])}>{t(status)}</span>;
}

/** What a task says on screen. A security task reads as the upgrade it stands for. */
export function useTaskTitle() {
  const t = useTranslations("tasks");
  return (task: Pick<Task, "title" | "kind" | "security">): string => {
    const s = task.security;
    // Only while the title is still the package name (nobody renamed it).
    if (task.kind !== "security" || !s || task.title !== s.label) return task.title;
    if (s.upgrade?.version) return t("upgradeTo", { name: task.title, version: s.upgrade.version });
    if (s.subject === "runtime" && s.installed.length) return t("upgradeRuntime", { name: task.title, version: s.installed[0] });
    return t("upgrade", { name: task.title });
  };
}

export function DueLabel({ task }: { task: Pick<Task, "effective_due" | "overdue" | "due_date" | "status"> }) {
  const t = useTranslations("tasks");
  if (!task.effective_due) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span
      className={cn("text-xs tabular-nums whitespace-nowrap", task.overdue && "font-semibold text-red-600 dark:text-red-400")}
      title={task.due_date ? undefined : t("dueFromSla")}
    >
      {shortDate(task.effective_due)}
      {!task.due_date && " *"}
    </span>
  );
}

export function Initials({ user }: { user: UserBrief | null }) {
  const t = useTranslations("tasks");
  if (!user) return <span className="text-xs text-muted-foreground">{t("unassigned")}</span>;
  const name = userLabel(user);
  return (
    <span className="inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
      <span className="grid size-6 place-items-center rounded-full bg-muted text-[10px] font-semibold">
        {name.slice(0, 2).toUpperCase()}
      </span>
      {name}
    </span>
  );
}

/** People who can take a task: project members with write access. */
export function useAssignees(projectId: string) {
  const { data } = useApi<Member[]>(`/projects/${projectId}/members`);
  return (data ?? [])
    .filter((m) => m.role !== "viewer")
    .map<UserBrief>((m) => ({ id: m.user_id, email: m.email, display_name: m.display_name, company_id: m.company_id }));
}

export type TaskDraft = Partial<Pick<Task, "kind" | "status" | "start_date" | "due_date" | "sprint_id" | "parent_id">>;

export function TaskDialog({
  projectId,
  task,
  draft,
  tasks,
  sprints,
  onClose,
  onSaved,
  canWrite = true,
}: {
  projectId: string;
  task: Task | null;
  draft?: TaskDraft;
  tasks?: Task[];
  sprints?: Sprint[];
  onClose: () => void;
  onSaved: () => void;
  canWrite?: boolean;
}) {
  const t = useTranslations();
  const assignees = useAssignees(projectId);
  const titleOf = useTaskTitle();
  const [title, setTitle] = useState(task?.title ?? "");
  const [kind, setKind] = useState<TaskKind>(task?.kind ?? draft?.kind ?? "development");
  const [status, setStatus] = useState<TaskStatus>(task?.status ?? draft?.status ?? "todo");
  const [assignee, setAssignee] = useState(task?.assignee?.id ?? "");
  const [startDate, setStartDate] = useState(task?.start_date ?? draft?.start_date ?? "");
  const [dueDate, setDueDate] = useState(task?.due_date ?? draft?.due_date ?? "");
  const [parentId, setParentId] = useState(task?.parent_id ?? draft?.parent_id ?? "");
  const [milestone, setMilestone] = useState(task?.is_milestone ?? false);
  const [progress, setProgress] = useState(String(task?.progress ?? 0));
  const [dependsOn, setDependsOn] = useState<string[]>(task?.depends_on ?? []);
  const [sprintId, setSprintId] = useState(task?.sprint_id ?? draft?.sprint_id ?? "");
  const [points, setPoints] = useState(task?.points?.toString() ?? "");
  const [hours, setHours] = useState(task?.estimate_hours?.toString() ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [error, setError] = useState<string | null>(null);

  const people = [...assignees];
  if (task?.assignee && !people.some((p) => p.id === task.assignee!.id)) people.unshift(task.assignee);
  const others = (tasks ?? []).filter((o) => o.id !== task?.id);
  const phases = others.filter((o) => !o.is_milestone);
  const openSprints = (sprints ?? []).filter((s) => s.status !== "closed" || s.id === sprintId);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      title,
      kind,
      status,
      assignee_id: assignee || null,
      start_date: startDate || null,
      due_date: milestone ? startDate || dueDate || null : dueDate || null,
      parent_id: parentId || null,
      is_milestone: milestone,
      progress: Math.max(0, Math.min(100, Number(progress) || 0)),
      depends_on: dependsOn,
      sprint_id: sprintId || null,
      points: points === "" ? null : Number(points),
      estimate_hours: hours === "" ? null : Number(hours),
      description: description || null,
    };
    if (milestone && !body.start_date) body.start_date = body.due_date;
    try {
      await api(task ? `/tasks/${task.id}` : `/projects/${projectId}/tasks`, {
        method: task ? "PATCH" : "POST",
        json: body,
      });
      toast.success(t("common.saved"));
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove() {
    if (!task || !confirm(t("tasks.confirmDelete", { title: titleOf(task) }))) return;
    try {
      await api(`/tasks/${task.id}`, { method: "DELETE" });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{task ? `#${task.number} ${titleOf(task)}` : t("tasks.add")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <fieldset disabled={!canWrite}>
            <FieldGroup>
              <LabeledField label={t("tasks.title")} htmlFor="task-title">
                <Input
                  id="task-title"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={t("tasks.titlePlaceholder")}
                />
              </LabeledField>
              <div className="grid gap-4 sm:grid-cols-3">
                <LabeledField label={t("tasks.kind")}>
                  <OptionSelect
                    value={kind}
                    onValueChange={(v) => setKind(v as TaskKind)}
                    options={TASK_KINDS.map((k) => ({ value: k, label: t(`labels.taskKind.${k}`) }))}
                  />
                </LabeledField>
                <LabeledField label={t("tasks.status")}>
                  <OptionSelect
                    value={status}
                    onValueChange={(v) => setStatus(v as TaskStatus)}
                    options={TASK_STATUSES.map((s) => ({ value: s, label: t(`labels.taskStatus.${s}`) }))}
                  />
                </LabeledField>
                <LabeledField label={t("tasks.assignee")}>
                  <OptionSelect
                    value={assignee}
                    onValueChange={setAssignee}
                    options={[{ value: "", label: t("tasks.unassigned") }, ...people.map((p) => ({ value: p.id, label: userLabel(p) }))]}
                  />
                </LabeledField>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <LabeledField label={t("tasks.startDate")} htmlFor="task-start">
                  <Input id="task-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                </LabeledField>
                {!milestone && (
                  <LabeledField label={t("tasks.dueDate")} htmlFor="task-due">
                    <Input id="task-due" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
                  </LabeledField>
                )}
                <LabeledField label={t("tasks.progress")} htmlFor="task-progress">
                  <Input
                    id="task-progress"
                    type="number"
                    min={0}
                    max={100}
                    step={10}
                    value={progress}
                    onChange={(e) => setProgress(e.target.value)}
                  />
                </LabeledField>
              </div>
              <Label className="flex items-center gap-2 font-normal">
                <Checkbox checked={milestone} onCheckedChange={(v) => setMilestone(!!v)} />
                {t("tasks.milestone")}
              </Label>
              {(tasks?.length ?? 0) > 0 && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <LabeledField label={t("tasks.parent")}>
                    <OptionSelect
                      value={parentId}
                      onValueChange={setParentId}
                      options={[
                        { value: "", label: t("tasks.noParent") },
                        ...phases.map((p) => ({ value: p.id, label: `#${p.number} ${titleOf(p)}` })),
                      ]}
                    />
                  </LabeledField>
                  <LabeledField label={t("tasks.dependsOn")}>
                    <div className="grid max-h-32 gap-1 overflow-y-auto rounded-md border p-2">
                      {others.map((o) => (
                        <Label key={o.id} className="flex items-center gap-2 text-xs font-normal">
                          <Checkbox
                            checked={dependsOn.includes(o.id)}
                            onCheckedChange={(v) =>
                              setDependsOn(v ? [...dependsOn, o.id] : dependsOn.filter((d) => d !== o.id))
                            }
                          />
                          #{o.number} {titleOf(o)}
                        </Label>
                      ))}
                    </div>
                  </LabeledField>
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-3">
                {sprints && (
                  <LabeledField label={t("tasks.sprint")}>
                    <OptionSelect
                      value={sprintId}
                      onValueChange={setSprintId}
                      options={[
                        { value: "", label: t("tasks.backlog") },
                        ...openSprints.map((s) => ({ value: s.id, label: s.name })),
                      ]}
                    />
                  </LabeledField>
                )}
                {sprints && (
                  <LabeledField label={t("tasks.points")} htmlFor="task-points">
                    <Input id="task-points" type="number" min={0} step={1} value={points} onChange={(e) => setPoints(e.target.value)} />
                  </LabeledField>
                )}
                <LabeledField label={t("tasks.estimateHours")} htmlFor="task-hours">
                  <Input id="task-hours" type="number" min={0} step={0.5} value={hours} onChange={(e) => setHours(e.target.value)} />
                </LabeledField>
              </div>
              <LabeledField label={t("tasks.description")} htmlFor="task-desc">
                <Textarea id="task-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
              </LabeledField>
              <ErrorText>{error}</ErrorText>
              {canWrite && (
                <DialogFooter className="sm:justify-between">
                  {task ? (
                    <Button type="button" variant="ghost" className="text-destructive" onClick={remove}>
                      {t("common.delete")}
                    </Button>
                  ) : (
                    <span />
                  )}
                  <Button type="submit">{t("common.save")}</Button>
                </DialogFooter>
              )}
            </FieldGroup>
          </fieldset>
        </form>
      </DialogContent>
    </Dialog>
  );
}
