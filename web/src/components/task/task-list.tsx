"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { TASK_KINDS, todayISO, type Task, type TaskKind } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, OptionSelect, SeverityBadge } from "@/components/common";
import { EolBadge } from "@/components/eol-table";
import { userLabel } from "@/components/sales/status";
import {
  DueLabel,
  Initials,
  IssueLink,
  TaskKindBadge,
  TaskPriorityBadge,
  TaskStatusBadge,
  useTaskTitle,
} from "@/components/task/task-common";

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

type Group = "overdue" | "thisWeek" | "later" | "none" | "done";

function groupOf(task: Task, weekEnd: string): Group {
  if (task.status === "done") return "done";
  if (task.overdue) return "overdue";
  if (!task.effective_due) return "none";
  return task.effective_due <= weekEnd ? "thisWeek" : "later";
}

/** Simple list for maintenance: grouped by due date or by assignee. */
export function TaskList({
  tasks,
  onOpen,
  showProject = false,
}: {
  tasks: Task[];
  onOpen: (t: Task) => void;
  showProject?: boolean;
}) {
  const t = useTranslations();
  const [assignee, setAssignee] = useState("");
  const [kind, setKind] = useState<TaskKind | "">("");
  const [sort, setSort] = useState<"due" | "assignee">("due");
  const [showDone, setShowDone] = useState(false);

  const people = new Map(tasks.filter((x) => x.assignee).map((x) => [x.assignee!.id, x.assignee!]));
  const visible = tasks.filter(
    (x) =>
      (showDone || x.status !== "done") &&
      (!kind || x.kind === kind) &&
      (!assignee || (assignee === "none" ? !x.assignee : x.assignee?.id === assignee)),
  );
  const byDue = (a: Task, b: Task) => (a.effective_due ?? "9999").localeCompare(b.effective_due ?? "9999") || a.number - b.number;

  // Days until Sunday (weeks start on Monday).
  const today = todayISO();
  const dow = new Date(`${today}T00:00:00Z`).getUTCDay();
  const weekEnd = addDays(today, (7 - dow) % 7);

  let groups: { key: string; label: string; tasks: Task[]; danger?: boolean }[];
  if (sort === "due") {
    const order: Group[] = ["overdue", "thisWeek", "later", "none", "done"];
    groups = order.map((g) => ({
      key: g,
      label: t(`tasks.group.${g}`),
      tasks: visible.filter((x) => groupOf(x, weekEnd) === g).sort(byDue),
      danger: g === "overdue",
    }));
  } else {
    const keys = [...new Set(visible.map((x) => x.assignee?.id ?? ""))];
    groups = keys
      .map((k) => ({
        key: k || "none",
        label: k ? userLabel(people.get(k)) : t("tasks.unassigned"),
        tasks: visible.filter((x) => (x.assignee?.id ?? "") === k).sort(byDue),
      }))
      .sort((a, b) => (a.key === "none" ? 1 : b.key === "none" ? -1 : a.label.localeCompare(b.label)));
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <OptionSelect
          value={assignee}
          onValueChange={setAssignee}
          options={[
            { value: "", label: t("tasks.allAssignees") },
            ...[...people.values()].map((p) => ({ value: p.id, label: userLabel(p) })),
            { value: "none", label: t("tasks.unassigned") },
          ]}
        />
        <OptionSelect
          value={kind}
          onValueChange={(v) => setKind(v as TaskKind | "")}
          options={[{ value: "", label: t("tasks.allKinds") }, ...TASK_KINDS.map((k) => ({ value: k, label: t(`labels.taskKind.${k}`) }))]}
        />
        <OptionSelect
          value={sort}
          onValueChange={(v) => setSort(v as "due" | "assignee")}
          options={[
            { value: "due", label: t("tasks.sort.due") },
            { value: "assignee", label: t("tasks.sort.assignee") },
          ]}
        />
        <Label className="flex items-center gap-2 text-sm font-normal">
          <Checkbox checked={showDone} onCheckedChange={(v) => setShowDone(!!v)} />
          {t("tasks.showDone")}
        </Label>
      </div>
      {visible.length === 0 ? (
        <Empty>{t("tasks.empty")}</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("tasks.task")}</TableHead>
              <TableHead>{t("tasks.assignee")}</TableHead>
              <TableHead>{t("tasks.dueDate")}</TableHead>
              <TableHead>{t("tasks.status")}</TableHead>
              <TableHead className="text-right">{t("tasks.estimateHours")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {groups
              .filter((g) => g.tasks.length > 0)
              .flatMap((g) => [
                <TableRow key={`g-${g.key}`} className="bg-muted/40 hover:bg-muted/40">
                  <TableCell colSpan={5} className={cn("py-1.5 text-xs font-semibold", g.danger && "text-red-600 dark:text-red-400")}>
                    {g.label} <span className="font-normal text-muted-foreground">{g.tasks.length}</span>
                  </TableCell>
                </TableRow>,
                ...g.tasks.map((task) => <TaskRow key={task.id} task={task} onOpen={onOpen} showProject={showProject} />),
              ])}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

export function TaskRow({ task, onOpen, showProject }: { task: Task; onOpen: (t: Task) => void; showProject?: boolean }) {
  const titleOf = useTaskTitle();
  return (
    <TableRow className="cursor-pointer" onClick={() => onOpen(task)}>
      <TableCell>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={cn("font-medium", task.status === "done" && "text-muted-foreground line-through")}>{titleOf(task)}</span>
          <TaskKindBadge kind={task.kind} />
          <TaskPriorityBadge priority={task.priority} />
          <SecurityTags task={task} />
          <IssueLink task={task} />
        </div>
        {showProject && <div className="text-xs text-muted-foreground">{task.project_name} ・ #{task.number}</div>}
      </TableCell>
      <TableCell>
        <Initials user={task.assignee} />
      </TableCell>
      <TableCell>
        <DueLabel task={task} />
      </TableCell>
      <TableCell>
        <TaskStatusBadge status={task.status} />
      </TableCell>
      <TableCell className="text-right text-xs tabular-nums">{task.estimate_hours != null ? `${task.estimate_hours}h` : "—"}</TableCell>
    </TableRow>
  );
}

export function SecurityTags({ task }: { task: Pick<Task, "security"> }) {
  const t = useTranslations("security");
  const s = task.security;
  if (!s) return null;
  return (
    <>
      {s.max_severity && <SeverityBadge severity={s.max_severity} />}
      {s.vuln_count > 0 && <span className="text-xs text-muted-foreground">{t("vulnCount", { count: s.vuln_count })}</span>}
      {s.eol_status && <EolBadge status={s.eol_status} />}
    </>
  );
}
