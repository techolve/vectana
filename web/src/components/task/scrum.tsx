"use client";

import { useState } from "react";
import { CheckIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { api, TASK_STATUSES, todayISO, type Burndown, type Sprint, type Task, type Velocity } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Empty, ErrorText, LabeledField, OptionSelect } from "@/components/common";
import { shortDate } from "@/components/sales/status";
import {
  IssueLink,
  STATUS_STYLE,
  TaskKindBadge,
  TaskPriorityBadge,
  type TaskDraft,
  useTaskTitle,
} from "@/components/task/task-common";
import { SecurityTags } from "@/components/task/task-list";

export function ScrumBoard({
  projectId,
  tasks,
  sprints,
  canWrite,
  onOpen,
  onAdd,
  onChanged,
}: {
  projectId: string;
  tasks: Task[];
  sprints: Sprint[];
  canWrite: boolean;
  onOpen: (t: Task) => void;
  onAdd: (draft: TaskDraft) => void;
  onChanged: () => void;
}) {
  const t = useTranslations();
  const defaultSprint = sprints.find((s) => s.status === "active") ?? sprints.find((s) => s.status === "planned") ?? sprints.at(-1);
  const [chosen, setChosen] = useState<string | null>(null);
  const sprint = sprints.find((s) => s.id === chosen) ?? defaultSprint;
  const [editing, setEditing] = useState<Sprint | "new" | null>(null);

  async function patchTask(task: Task | string, body: Record<string, unknown>) {
    try {
      await api(`/tasks/${typeof task === "string" ? task : task.id}`, { method: "PATCH", json: body });
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function patchSprint(s: Sprint, body: Record<string, unknown>) {
    try {
      await api(`/sprints/${s.id}`, { method: "PATCH", json: body });
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const backlog = tasks.filter((x) => !x.sprint_id && x.status !== "done");
  const inSprint = sprint ? tasks.filter((x) => x.sprint_id === sprint.id) : [];

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {sprints.length > 0 && (
          <OptionSelect
            value={sprint?.id ?? ""}
            onValueChange={setChosen}
            options={sprints.map((s) => ({ value: s.id, label: `${s.name}（${t(`sprints.status.${s.status}`)}）` }))}
          />
        )}
        {sprint && (
          <span className="text-sm text-muted-foreground">
            {t("sprints.period", { start: shortDate(sprint.starts_on), end: shortDate(sprint.ends_on) })}
          </span>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          {canWrite && sprint && sprint.status === "planned" && (
            <Button variant="outline" onClick={() => patchSprint(sprint, { status: "active" })}>
              {t("sprints.start")}
            </Button>
          )}
          {canWrite && sprint && sprint.status === "active" && (
            <Button
              variant="outline"
              onClick={() => confirm(t("sprints.confirmClose", { name: sprint.name })) && patchSprint(sprint, { status: "closed" })}
            >
              {t("sprints.close")}
            </Button>
          )}
          {canWrite && sprint && (
            <Button variant="ghost" size="icon" aria-label={t("sprints.edit")} onClick={() => setEditing(sprint)}>
              <PencilIcon />
            </Button>
          )}
          {canWrite && (
            <Button variant="outline" onClick={() => setEditing("new")}>
              <PlusIcon /> {t("sprints.new")}
            </Button>
          )}
        </div>
      </div>

      {!sprint ? (
        <Empty>{t("sprints.none")}</Empty>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="gap-4 py-4">
              <CardHeader>
                <CardTitle>{t("sprints.goal")}</CardTitle>
                <CardDescription className="whitespace-pre-wrap">{sprint.goal || "—"}</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-1.5">
                <div className="text-xs font-medium text-muted-foreground">{t("sprints.dod")}</div>
                {sprint.definition_of_done.length === 0 && <span className="text-xs text-muted-foreground">—</span>}
                {sprint.definition_of_done.map((item, i) => (
                  <label key={i} className="flex items-start gap-2 text-sm">
                    <Checkbox
                      checked={item.done}
                      disabled={!canWrite}
                      onCheckedChange={(v) =>
                        patchSprint(sprint, {
                          definition_of_done: sprint.definition_of_done.map((d, j) => (j === i ? { ...d, done: !!v } : d)),
                        })
                      }
                    />
                    <span className={cn(item.done && "text-muted-foreground line-through")}>{item.text}</span>
                  </label>
                ))}
              </CardContent>
            </Card>
            <BurndownCard sprint={sprint} version={inSprint.map((x) => x.status + x.points).join()} />
            <VelocityCard projectId={projectId} version={sprints.map((s) => s.status + s.done_points).join()} />
          </div>

          <div className="grid gap-3 lg:grid-cols-4">
            <Column
              title={t("tasks.backlog")}
              count={backlog.length}
              points={backlog.reduce((s, x) => s + (x.points ?? 0), 0)}
              onDrop={(id) => patchTask(id, { sprint_id: null })}
              canDrop={canWrite}
              footer={
                canWrite && (
                  <Button variant="ghost" size="sm" className="w-full" onClick={() => onAdd({ sprint_id: null })}>
                    <PlusIcon /> {t("tasks.add")}
                  </Button>
                )
              }
            >
              {backlog.map((task) => (
                <Card_ key={task.id} task={task} onOpen={onOpen} draggable={canWrite}>
                  {canWrite && sprint.status !== "closed" && (
                    <Button
                      size="xs"
                      variant="ghost"
                      className="-mr-1"
                      onClick={(e) => {
                        e.stopPropagation();
                        patchTask(task, { sprint_id: sprint.id });
                      }}
                    >
                      {t("sprints.moveToSprint")} →
                    </Button>
                  )}
                </Card_>
              ))}
            </Column>
            {TASK_STATUSES.map((status) => {
              const list = inSprint.filter((x) => x.status === status).sort((a, b) => a.position - b.position);
              return (
                <Column
                  key={status}
                  title={t(`labels.taskStatus.${status}`)}
                  count={list.length}
                  points={list.reduce((s, x) => s + (x.points ?? 0), 0)}
                  accent={STATUS_STYLE[status]}
                  canDrop={canWrite && sprint.status !== "closed"}
                  onDrop={(id) => patchTask(id, { sprint_id: sprint.id, status })}
                  footer={
                    canWrite &&
                    status === "todo" &&
                    sprint.status !== "closed" && (
                      <Button variant="ghost" size="sm" className="w-full" onClick={() => onAdd({ sprint_id: sprint.id, status })}>
                        <PlusIcon /> {t("tasks.add")}
                      </Button>
                    )
                  }
                >
                  {list.map((task) => (
                    <Card_ key={task.id} task={task} onOpen={onOpen} draggable={canWrite && sprint.status !== "closed"} />
                  ))}
                </Column>
              );
            })}
          </div>
        </>
      )}

      {editing && (
        <SprintDialog
          projectId={projectId}
          sprint={editing === "new" ? null : editing}
          count={sprints.length}
          onClose={() => setEditing(null)}
          onSaved={(s) => {
            setEditing(null);
            if (s) setChosen(s.id);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function plusDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function Column({
  title,
  count,
  points,
  accent,
  canDrop,
  onDrop,
  footer,
  children,
}: {
  title: string;
  count: number;
  points: number;
  accent?: string;
  canDrop: boolean;
  onDrop: (taskId: string) => void;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  const t = useTranslations("sprints");
  const [over, setOver] = useState(false);
  return (
    <section
      className={cn("flex min-h-40 flex-col gap-2 rounded-lg border bg-muted/30 p-2", over && "ring-2 ring-primary/40")}
      onDragOver={(e) => {
        if (!canDrop) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        const id = e.dataTransfer.getData("text/plain");
        if (id) onDrop(id);
      }}
    >
      <header className="flex items-center justify-between px-1">
        <span className={cn("rounded px-1.5 py-0.5 text-xs font-semibold", accent)}>{title}</span>
        <span className="text-xs text-muted-foreground tabular-nums">{t("summary", { count, points })}</span>
      </header>
      {children}
      {footer}
    </section>
  );
}

function Card_({
  task,
  onOpen,
  draggable,
  children,
}: {
  task: Task;
  onOpen: (t: Task) => void;
  draggable: boolean;
  children?: React.ReactNode;
}) {
  const titleOf = useTaskTitle();
  return (
    <div
      role="button"
      tabIndex={0}
      draggable={draggable}
      onDragStart={(e) => e.dataTransfer.setData("text/plain", task.id)}
      onClick={() => onOpen(task)}
      onKeyDown={(e) => e.key === "Enter" && onOpen(task)}
      className={cn(
        "grid gap-1.5 rounded-md border bg-card p-2.5 text-sm shadow-xs hover:border-primary/40",
        draggable && "cursor-grab",
        task.overdue && "border-red-500/50",
      )}
    >
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="tabular-nums">#{task.number}</span>
        {task.kind !== "development" && <TaskKindBadge kind={task.kind} />}
        <TaskPriorityBadge priority={task.priority} />
        <IssueLink task={task} />
        <span className="ml-auto font-medium tabular-nums">{task.points != null ? `${task.points} pt` : ""}</span>
      </div>
      <div className={cn("font-medium", task.status === "done" && "text-muted-foreground line-through")}>{titleOf(task)}</div>
      <div className="flex flex-wrap items-center gap-1.5">
        <SecurityTags task={task} />
        {task.assignee && (
          <span className="ml-auto grid size-6 place-items-center rounded-full bg-muted text-[10px] font-semibold" title={task.assignee.display_name ?? task.assignee.email}>
            {(task.assignee.display_name || task.assignee.email).slice(0, 2).toUpperCase()}
          </span>
        )}
        {children}
      </div>
    </div>
  );
}

function BurndownCard({ sprint, version }: { sprint: Sprint; version: string }) {
  const t = useTranslations("sprints");
  const { data } = useApi<Burndown>(`/sprints/${sprint.id}/burndown?v=${encodeURIComponent(version)}`);
  if (!data) return <Card className="gap-4 py-4" />;
  const w = 320;
  const h = 140;
  const pad = 4;
  const n = Math.max(data.points.length - 1, 1);
  const max = Math.max(data.total, 1);
  const px = (i: number) => pad + (i / n) * (w - pad * 2);
  const py = (v: number) => pad + (1 - v / max) * (h - pad * 2);
  const ideal = data.points.map((p, i) => `${px(i)},${py(p.ideal)}`).join(" ");
  const actual = data.points
    .map((p, i) => (p.remaining == null ? null : `${px(i)},${py(p.remaining)}`))
    .filter(Boolean)
    .join(" ");
  const last = [...data.points].reverse().find((p) => p.remaining != null);
  const unit = t(`unit.${data.unit}`);
  return (
    <Card className="gap-4 py-4">
      <CardHeader>
        <CardTitle>{t("burndown")}</CardTitle>
        <CardDescription>
          {t("remaining", { remaining: last?.remaining ?? data.total, total: data.total, unit })}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <svg viewBox={`0 0 ${w} ${h}`} className="h-36 w-full" role="img" aria-label={t("burndown")}>
          <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} className="stroke-border" />
          <polyline points={ideal} fill="none" strokeDasharray="4 4" strokeWidth={1.5} className="stroke-muted-foreground" />
          {actual && <polyline points={actual} fill="none" strokeWidth={2.5} className="stroke-primary" />}
        </svg>
        <div className="mt-1 flex gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="h-0.5 w-4 bg-primary" /> {t("actual")}
          </span>
          <span className="flex items-center gap-1">
            <span className="h-0 w-4 border-t border-dashed border-muted-foreground" /> {t("ideal")}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function VelocityCard({ projectId, version }: { projectId: string; version: string }) {
  const t = useTranslations("sprints");
  const { data } = useApi<Velocity[]>(`/projects/${projectId}/velocity?v=${encodeURIComponent(version)}`);
  if (!data) return <Card className="gap-4 py-4" />;
  const recent = data.slice(-6);
  const closed = recent.filter((v) => v.status === "closed").slice(-4);
  const avg = closed.length ? closed.reduce((s, v) => s + v.completed, 0) / closed.length : null;
  const max = Math.max(1, ...recent.map((v) => Math.max(v.committed, v.completed)));
  return (
    <Card className="gap-4 py-4">
      <CardHeader>
        <CardTitle>{t("velocity")}</CardTitle>
        <CardDescription>
          {avg != null ? (
            <>
              {t("avgVelocity", { count: closed.length })}{" "}
              <span className="text-base font-semibold text-foreground tabular-nums">{Math.round(avg * 10) / 10}</span> pt
            </>
          ) : (
            t("noVelocity")
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex h-36 items-end gap-3">
          {recent.map((v) => (
            <div key={v.sprint_id} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex h-28 w-full items-end justify-center gap-0.5">
                <div className="w-3 rounded-t bg-muted-foreground/30" style={{ height: `${(v.committed / max) * 100}%` }} title={`${t("committed")} ${v.committed}`} />
                <div className="w-3 rounded-t bg-primary" style={{ height: `${(v.completed / max) * 100}%` }} title={`${t("completed")} ${v.completed}`} />
              </div>
              <span className="max-w-full truncate text-[10px] text-muted-foreground">{v.name}</span>
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-sm bg-muted-foreground/30" /> {t("committed")}
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-sm bg-primary" /> {t("completed")}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function SprintDialog({
  projectId,
  sprint,
  count,
  onClose,
  onSaved,
}: {
  projectId: string;
  sprint: Sprint | null;
  count: number;
  onClose: () => void;
  onSaved: (s: Sprint | null) => void;
}) {
  const t = useTranslations();
  const today = todayISO();
  const twoWeeks = plusDays(today, 13);
  const [name, setName] = useState(sprint?.name ?? `Sprint ${count + 1}`);
  const [goal, setGoal] = useState(sprint?.goal ?? "");
  const [startsOn, setStartsOn] = useState(sprint?.starts_on ?? today);
  const [endsOn, setEndsOn] = useState(sprint?.ends_on ?? twoWeeks);
  const [dod, setDod] = useState(sprint?.definition_of_done ?? []);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      name,
      goal: goal || null,
      starts_on: startsOn,
      ends_on: endsOn,
      definition_of_done: dod.filter((d) => d.text.trim()),
    };
    try {
      const saved = await api<Sprint>(sprint ? `/sprints/${sprint.id}` : `/projects/${projectId}/sprints`, {
        method: sprint ? "PATCH" : "POST",
        json: body,
      });
      onSaved(saved);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove() {
    if (!sprint || !confirm(t("tasks.confirmDelete", { title: sprint.name }))) return;
    await api(`/sprints/${sprint.id}`, { method: "DELETE" });
    onSaved(null);
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{sprint ? t("sprints.edit") : t("sprints.new")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <FieldGroup>
            <LabeledField label={t("sprints.name")} htmlFor="sprint-name">
              <Input id="sprint-name" required value={name} onChange={(e) => setName(e.target.value)} />
            </LabeledField>
            <div className="grid gap-4 sm:grid-cols-2">
              <LabeledField label={t("sprints.startsOn")} htmlFor="sprint-start">
                <Input id="sprint-start" type="date" required value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
              </LabeledField>
              <LabeledField label={t("sprints.endsOn")} htmlFor="sprint-end">
                <Input id="sprint-end" type="date" required value={endsOn} onChange={(e) => setEndsOn(e.target.value)} />
              </LabeledField>
            </div>
            <LabeledField label={t("sprints.goal")} htmlFor="sprint-goal">
              <Textarea id="sprint-goal" value={goal} onChange={(e) => setGoal(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("sprints.dod")}>
              <div className="grid gap-2">
                {dod.map((d, i) => (
                  <div key={i} className="flex items-center gap-2">
                    {d.done && <CheckIcon className="size-4 text-emerald-600" />}
                    <Input
                      value={d.text}
                      placeholder={t("sprints.dodPlaceholder")}
                      onChange={(e) => setDod(dod.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))}
                    />
                    <Button type="button" variant="ghost" size="icon" aria-label={t("common.delete")} onClick={() => setDod(dod.filter((_, j) => j !== i))}>
                      <Trash2Icon />
                    </Button>
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => setDod([...dod, { text: "", done: false }])}>
                  <PlusIcon /> {t("sprints.addDod")}
                </Button>
              </div>
            </LabeledField>
            <ErrorText>{error}</ErrorText>
            <DialogFooter className="sm:justify-between">
              {sprint ? (
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

