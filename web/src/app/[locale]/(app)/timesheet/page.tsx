"use client";

import { useEffect, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon, CopyIcon, PlusIcon, SendIcon, Trash2Icon, Undo2Icon } from "lucide-react";
import { toast } from "sonner";
import { useLocale, useTranslations } from "next-intl";

import {
  addDaysISO,
  api,
  mondayISO,
  todayISO,
  type Project,
  type Task,
  type Timesheet,
  type TimesheetRow,
  type UserBrief,
} from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorText, LabeledField, OptionSelect, PageHeader } from "@/components/common";
import { userLabel } from "@/components/sales/status";
import { TaskKindBadge, useTaskTitle } from "@/components/task/task-common";

type Draft = Omit<TimesheetRow, "hours"> & {
  key: string;
  hours: string[];
  saved: number; // this row's hours of the week as last saved (part of actual_hours)
};

const rowKey = (r: Pick<TimesheetRow, "project_id" | "task_id" | "label">) =>
  `${r.project_id ?? ""}|${r.task_id ?? ""}|${r.label ?? ""}`;

function toDraft(r: TimesheetRow): Draft {
  return {
    ...r,
    key: rowKey(r),
    hours: r.hours.map((h) => (h ? String(h) : "")),
    saved: r.hours.reduce<number>((s, h) => s + (h ?? 0), 0),
  };
}

const num = (v: string) => Number(v) || 0;
const fmt = (n: number) => (Math.round(n * 100) / 100).toString();

export default function TimesheetPage() {
  const t = useTranslations("timesheet");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [week, setWeek] = useState(() => mondayISO(todayISO()));
  const [userId, setUserId] = useState("");
  const { data: people } = useApi<UserBrief[]>("/timesheet/people");
  const query = `/timesheet?week=${week}${userId ? `&user_id=${userId}` : ""}`;
  const { data: sheet, error, reload } = useApi<Timesheet>(query);
  const [rows, setRows] = useState<Draft[]>([]);
  const [loadedFor, setLoadedFor] = useState<Timesheet | null>(null);
  const [dirty, setDirty] = useState(false);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);

  // Reset the grid whenever a sheet arrives from the server.
  if (sheet && sheet !== loadedFor) {
    setLoadedFor(sheet);
    setRows(sheet.rows.map(toDraft));
    setDirty(false);
  }

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const editable = !!sheet?.can_edit;
  const days = sheet?.days ?? Array.from({ length: 7 }, (_, i) => addDaysISO(week, i));
  const dayTotals = days.map((_, i) => rows.reduce((s, r) => s + num(r.hours[i]), 0));
  const weekTotal = dayTotals.reduce((a, b) => a + b, 0);
  const standard = sheet?.standard_hours ?? 40;
  const today = todayISO();

  const update = (next: Draft[]) => {
    setRows(next);
    setDirty(true);
  };
  const setCell = (r: number, d: number, v: string) =>
    update(rows.map((row, i) => (i === r ? { ...row, hours: row.hours.map((h, j) => (j === d ? v : h)) } : row)));

  /** Paste a block copied from Excel or a sheet (tab and newline separated). */
  function paste(e: React.ClipboardEvent<HTMLInputElement>, r: number, d: number) {
    const text = e.clipboardData.getData("text/plain");
    if (!/[\t\n]/.test(text.trim())) return;
    e.preventDefault();
    const lines = text.replace(/\r/g, "").replace(/\n$/, "").split("\n");
    const next = rows.map((row) => ({ ...row, hours: [...row.hours] }));
    lines.forEach((line, i) => {
      const row = next[r + i];
      if (!row) return;
      line.split("\t").forEach((cell, j) => {
        if (d + j > 6) return;
        const v = cell.trim().replace(/h$/i, "");
        row.hours[d + j] = v === "" || Number.isNaN(Number(v)) ? "" : String(Number(v));
      });
    });
    update(next);
    if (lines.length > rows.length - r) toast.warning(t("pasteTooMany"));
  }

  function go(to: string) {
    if (dirty && !confirm(t("discard"))) return;
    setWeek(mondayISO(to));
  }

  async function save(): Promise<Timesheet | null> {
    setBusy(true);
    try {
      const saved = await api<Timesheet>("/timesheet", {
        method: "PUT",
        json: {
          week_start: week,
          user_id: userId || null,
          rows: rows.map((r) => ({
            project_id: r.project_id,
            task_id: r.task_id,
            label: r.label,
            hours: r.hours.map((h) => (h === "" ? null : Number(h))),
          })),
        },
      });
      setLoadedFor(saved);
      setRows(saved.rows.map(toDraft));
      setDirty(false);
      toast.success(tc("saved"));
      reload();
      return saved;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function submit(undo: boolean) {
    if (!undo && dirty && !(await save())) return;
    try {
      await api(`/timesheet/submit?week=${week}${userId ? `&user_id=${userId}` : ""}`, {
        method: undo ? "DELETE" : "POST",
      });
      toast.success(undo ? t("unsubmitted") : t("submittedToast"));
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function copyLastWeek() {
    try {
      const prev = await api<Timesheet>(
        `/timesheet?week=${addDaysISO(week, -7)}${userId ? `&user_id=${userId}` : ""}`,
      );
      const have = new Set(rows.map((r) => r.key));
      const extra = prev.rows
        .filter((r) => !have.has(rowKey(r)))
        .map((r) => ({ ...toDraft({ ...r, hours: Array(7).fill(null) }), actual_hours: r.actual_hours }));
      if (!extra.length) {
        toast.info(t("nothingToCopy"));
        return;
      }
      update([...rows, ...extra]);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const weekday = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(locale, { weekday: "short" });
  const isWeekend = (i: number) => i >= 5;

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          people &&
          people.length > 1 && (
            <OptionSelect
              value={userId}
              onValueChange={(v) => {
                if (dirty && !confirm(t("discard"))) return;
                setUserId(v === people[0].id ? "" : v);
              }}
              options={people.map((p, i) => ({ value: i === 0 ? "" : p.id, label: userLabel(p) }))}
            />
          )
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center">
          <Button variant="outline" size="icon" aria-label={t("prevWeek")} onClick={() => go(addDaysISO(week, -7))}>
            <ChevronLeftIcon />
          </Button>
          <span className="min-w-44 px-3 text-center text-sm font-medium tabular-nums">
            {t("weekOf", { from: week.replaceAll("-", "/"), to: addDaysISO(week, 6).slice(5).replace("-", "/") })}
          </span>
          <Button variant="outline" size="icon" aria-label={t("nextWeek")} onClick={() => go(addDaysISO(week, 7))}>
            <ChevronRightIcon />
          </Button>
        </div>
        <Button variant="ghost" size="sm" onClick={() => go(today)}>
          {t("thisWeek")}
        </Button>
        {sheet?.submitted_at && (
          <span className="rounded-md bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
            {t("submitted")}
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {editable && (
            <>
              <Button variant="outline" size="sm" onClick={copyLastWeek}>
                <CopyIcon /> {t("copyLastWeek")}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
                <PlusIcon /> {t("addRow")}
              </Button>
            </>
          )}
        </div>
      </div>
      <ErrorText>{error}</ErrorText>
      {sheet && (
        <div className="overflow-x-auto rounded-lg border">
          <Table className="min-w-[860px]">
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 z-10 min-w-44 bg-background sm:min-w-56">{t("work")}</TableHead>
                {days.map((d, i) => (
                  <TableHead
                    key={d}
                    className={cn(
                      "w-16 text-center",
                      isWeekend(i) && "text-muted-foreground/70",
                      d === today && "text-primary",
                    )}
                  >
                    <div className="text-[11px] font-normal">{weekday(d)}</div>
                    <div className="tabular-nums">{d.slice(5).replace("-", "/").replace(/^0/, "")}</div>
                  </TableHead>
                ))}
                <TableHead className="w-16 text-right">{t("total")}</TableHead>
                <TableHead className="w-24 text-right">{t("remaining")}</TableHead>
                {editable && <TableHead className="w-10" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={11} className="py-8 text-center text-sm text-muted-foreground">
                    {editable ? t("emptyEditable") : t("empty")}
                  </TableCell>
                </TableRow>
              )}
              {rows.map((r, ri) => {
                const total = r.hours.reduce((s, h) => s + num(h), 0);
                const actual = (r.actual_hours ?? 0) - r.saved + total;
                const remaining = r.estimate_hours != null ? r.estimate_hours - actual : null;
                return (
                  <TableRow key={r.key}>
                    <TableCell className="sticky left-0 z-10 max-w-56 bg-background py-1.5">
                      <RowLabel row={r} />
                    </TableCell>
                    {r.hours.map((h, di) => (
                      <TableCell key={di} className={cn("p-1", isWeekend(di) && "bg-muted/40")}>
                        {editable ? (
                          <Input
                            inputMode="decimal"
                            aria-label={`${r.task_title ?? r.project_name ?? r.label} ${days[di]}`}
                            className="h-8 px-1 text-center tabular-nums"
                            value={h}
                            onChange={(e) => setCell(ri, di, e.target.value.replace(/[^\d.]/g, ""))}
                            onPaste={(e) => paste(e, ri, di)}
                          />
                        ) : (
                          <div className="text-center tabular-nums">{h || ""}</div>
                        )}
                      </TableCell>
                    ))}
                    <TableCell className="text-right font-medium tabular-nums">{total ? fmt(total) : ""}</TableCell>
                    <TableCell
                      className={cn("text-right text-xs tabular-nums", remaining != null && remaining < 0 && "text-destructive")}
                      title={r.estimate_hours != null ? t("estimateOf", { hours: r.estimate_hours }) : undefined}
                    >
                      {remaining != null ? t("hours", { hours: fmt(remaining) }) : "—"}
                    </TableCell>
                    {editable && (
                      <TableCell className="p-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={tc("delete")}
                          onClick={() => update(rows.filter((_, i) => i !== ri))}
                        >
                          <Trash2Icon />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell className="sticky left-0 z-10 bg-muted font-medium">{t("dayTotal")}</TableCell>
                {dayTotals.map((v, i) => (
                  <TableCell key={i} className={cn("text-center tabular-nums", v > 24 && "text-destructive")}>
                    {v ? fmt(v) : ""}
                  </TableCell>
                ))}
                <TableCell className="text-right font-semibold tabular-nums">{fmt(weekTotal)}</TableCell>
                <TableCell colSpan={editable ? 2 : 1} />
              </TableRow>
            </TableFooter>
          </Table>
        </div>
      )}
      {sheet && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <WeekGauge total={weekTotal} standard={standard} />
          {editable && <p className="text-xs text-muted-foreground">{t("pasteHint")}</p>}
          {editable && (
            <div className="ml-auto flex gap-2">
              <Button variant="outline" disabled={!dirty || busy} onClick={save}>
                {tc("save")}
              </Button>
              {sheet.submitted_at ? (
                <Button variant="outline" onClick={() => submit(true)}>
                  <Undo2Icon /> {t("unsubmit")}
                </Button>
              ) : (
                <Button disabled={busy} onClick={() => submit(false)}>
                  <SendIcon /> {t("submit")}
                </Button>
              )}
            </div>
          )}
        </div>
      )}
      {adding && (
        <AddRowDialog
          userId={userId || null}
          existing={new Set(rows.map((r) => r.key))}
          onClose={() => setAdding(false)}
          onAdd={(row) => {
            update([...rows, toDraft(row)]);
            setAdding(false);
          }}
        />
      )}
    </>
  );
}

function RowLabel({ row }: { row: Draft }) {
  const t = useTranslations("timesheet");
  if (!row.project_id) {
    return (
      <div>
        <div className="text-sm">{row.label}</div>
        <div className="text-xs text-muted-foreground">{t("outsideProjects")}</div>
      </div>
    );
  }
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5 text-sm">
        {row.task_kind && <TaskKindBadge kind={row.task_kind} />}
        <span className="truncate">
          {row.task_title ? (
            <>
              <span className="text-muted-foreground tabular-nums">#{row.task_number} </span>
              {row.task_title}
            </>
          ) : (
            t("noTask")
          )}
        </span>
      </div>
      <div className="truncate text-xs text-muted-foreground">{row.project_name}</div>
    </div>
  );
}

function WeekGauge({ total, standard }: { total: number; standard: number }) {
  const t = useTranslations("timesheet");
  const ratio = Math.min(total / standard, 1.25);
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="tabular-nums">{t("weekTotal", { total: fmt(total), standard })}</span>
      <div className="relative h-2 w-40 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div
          className={cn("h-full rounded-full", total > standard ? "bg-amber-500" : "bg-primary")}
          style={{ width: `${(ratio / 1.25) * 100}%` }}
        />
        <div className="absolute inset-y-0 w-px bg-foreground/40" style={{ left: `${100 / 1.25}%` }} />
      </div>
      {total > standard && <span className="text-xs text-amber-700 dark:text-amber-400">{t("over", { hours: fmt(total - standard) })}</span>}
    </div>
  );
}

function AddRowDialog({
  userId,
  existing,
  onClose,
  onAdd,
}: {
  userId: string | null;
  existing: Set<string>;
  onClose: () => void;
  onAdd: (row: TimesheetRow) => void;
}) {
  const t = useTranslations("timesheet");
  const tc = useTranslations("common");
  const taskTitle = useTaskTitle();
  const { data: projects } = useApi<Project[]>("/projects");
  const { data: mine } = useApi<Task[]>(userId ? null : "/tasks?scope=mine");
  const [projectId, setProjectId] = useState("");
  const [taskId, setTaskId] = useState("");
  const [label, setLabel] = useState("");
  const { data: tasks } = useApi<Task[]>(projectId ? `/projects/${projectId}/tasks` : null);
  const open = (projects ?? []).filter((p) => !p.archived);
  const project = open.find((p) => p.id === projectId);

  const base = { estimate_hours: null, actual_hours: null, hours: Array(7).fill(null) };
  const fromTask = (task: Task): TimesheetRow => ({
    ...base,
    project_id: task.project_id,
    project_name: task.project_name,
    task_id: task.id,
    task_number: task.number,
    task_title: taskTitle(task),
    task_kind: task.kind,
    label: null,
    estimate_hours: task.estimate_hours,
  });

  function add(e: React.FormEvent) {
    e.preventDefault();
    const task = tasks?.find((x) => x.id === taskId);
    const row: TimesheetRow = task
      ? fromTask(task)
      : project
        ? { ...base, project_id: project.id, project_name: project.name, task_id: null, task_number: null, task_title: null, task_kind: null, label: null }
        : { ...base, project_id: null, project_name: null, task_id: null, task_number: null, task_title: null, task_kind: null, label: label.trim() };
    if (!row.project_id && !row.label) return;
    if (existing.has(rowKey(row))) {
      toast.info(t("alreadyListed"));
      return;
    }
    onAdd(row);
  }

  const quick = (mine ?? []).filter((x) => x.status !== "done" && !existing.has(rowKey({ project_id: x.project_id, task_id: x.id, label: null })));

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("addRow")}</DialogTitle>
        </DialogHeader>
        {quick.length > 0 && (
          <div className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">{t("myTasks")}</span>
            <div className="flex max-h-40 flex-col gap-1 overflow-y-auto">
              {quick.slice(0, 20).map((task) => (
                <button
                  key={task.id}
                  type="button"
                  className="flex items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-muted"
                  onClick={() => onAdd(fromTask(task))}
                >
                  <PlusIcon className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate">{taskTitle(task)}</span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">{task.project_name}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        <form onSubmit={add}>
          <FieldGroup>
            <LabeledField label={t("project")}>
              <OptionSelect
                value={projectId}
                onValueChange={(v) => {
                  setProjectId(v);
                  setTaskId("");
                }}
                options={[{ value: "", label: t("outsideProjects") }, ...open.map((p) => ({ value: p.id, label: p.name }))]}
              />
            </LabeledField>
            {projectId ? (
              <LabeledField label={t("task")} hint={t("taskHint")}>
                <OptionSelect
                  value={taskId}
                  onValueChange={setTaskId}
                  options={[
                    { value: "", label: t("noTask") },
                    ...(tasks ?? [])
                      .filter((x) => x.status !== "done")
                      .map((x) => ({ value: x.id, label: `#${x.number} ${taskTitle(x)}` })),
                  ]}
                />
              </LabeledField>
            ) : (
              <LabeledField label={t("label")} htmlFor="ts-label">
                <Input
                  id="ts-label"
                  required
                  maxLength={200}
                  value={label}
                  placeholder={t("labelPlaceholder")}
                  onChange={(e) => setLabel(e.target.value)}
                />
              </LabeledField>
            )}
          </FieldGroup>
          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" onClick={onClose}>
              {tc("cancel")}
            </Button>
            <Button type="submit">{tc("add")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
