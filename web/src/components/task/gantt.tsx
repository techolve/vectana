"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { todayISO, type Task } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Empty } from "@/components/common";
import { DueLabel, TaskKindBadge, useTaskTitle } from "@/components/task/task-common";

const DAY = 86_400_000;
const ROW = 36;
const HEADER = 44;

function toDay(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Math.floor(Date.UTC(y, m - 1, d) / DAY);
}
function fromDay(day: number): Date {
  return new Date(day * DAY);
}

type Row = { task: Task; depth: number; start: number | null; end: number | null; isPhase: boolean };

/** Order tasks as a tree (phases first, children under them) and work out each bar. */
function buildRows(tasks: Task[]): Row[] {
  const children = new Map<string | null, Task[]>();
  const ids = new Set(tasks.map((t) => t.id));
  for (const t of tasks) {
    const parent = t.parent_id && ids.has(t.parent_id) ? t.parent_id : null;
    children.set(parent, [...(children.get(parent) ?? []), t]);
  }
  const order = (list: Task[]) =>
    [...list].sort((a, b) => (a.start_date ?? a.due_date ?? "9999").localeCompare(b.start_date ?? b.due_date ?? "9999") || a.number - b.number);
  const rows: Row[] = [];
  const span = (t: Task): [number | null, number | null] => {
    const s = t.start_date ? toDay(t.start_date) : t.due_date ? toDay(t.due_date) : null;
    const e = t.due_date ? toDay(t.due_date) : s;
    return [s, e];
  };
  const visit = (t: Task, depth: number, seen: Set<string>): [number | null, number | null] => {
    if (seen.has(t.id)) return [null, null];
    seen.add(t.id);
    const row: Row = { task: t, depth, start: null, end: null, isPhase: false };
    rows.push(row);
    let [s, e] = span(t);
    const kids = order(children.get(t.id) ?? []);
    for (const k of kids) {
      const [ks, ke] = visit(k, depth + 1, seen);
      if (ks != null) s = s == null ? ks : Math.min(s, ks);
      if (ke != null) e = e == null ? ke : Math.max(e, ke);
    }
    row.isPhase = kids.length > 0;
    row.start = s;
    row.end = e;
    return [s, e];
  };
  const seen = new Set<string>();
  for (const t of order(children.get(null) ?? [])) visit(t, 0, seen);
  return rows;
}

export function Gantt({ tasks, onOpen }: { tasks: Task[]; onOpen: (t: Task) => void }) {
  const t = useTranslations("tasks");
  const locale = useLocale();
  const titleOf = useTaskTitle();
  const [zoom, setZoom] = useState<"day" | "week">("day");
  const dayWidth = zoom === "day" ? 28 : 10;

  const rows = useMemo(() => buildRows(tasks), [tasks]);
  const today = toDay(todayISO());
  const scroller = useRef<HTMLDivElement>(null);
  const firstDay = rows.reduce((m, r) => (r.start != null ? Math.min(m, r.start) : m), today) - 3;
  // Open on this week rather than on the first task.
  useEffect(() => {
    if (scroller.current) scroller.current.scrollLeft = Math.max(0, (today - firstDay - 7) * dayWidth);
  }, [today, firstDay, dayWidth]);
  const scheduled = rows.filter((r) => r.start != null);
  if (tasks.length === 0) return <Empty>{t("empty")}</Empty>;

  const min = firstDay;
  const max = Math.max(today, ...scheduled.map((r) => r.end!)) + 7;
  const days = max - min + 1;
  const width = days * dayWidth;
  const x = (day: number) => (day - min) * dayWidth;
  const index = new Map(rows.map((r, i) => [r.task.id, i]));

  // Month labels and day / week ticks.
  const months: { left: number; label: string }[] = [];
  const ticks: { left: number; label: string; weekend: boolean }[] = [];
  for (let d = min; d <= max; d++) {
    const date = fromDay(d);
    if (d === min || date.getUTCDate() === 1) {
      months.push({ left: x(d), label: date.toLocaleDateString(locale, { year: "numeric", month: "short", timeZone: "UTC" }) });
    }
    const dow = date.getUTCDay();
    if (zoom === "day" || dow === 1) {
      ticks.push({ left: x(d), label: String(date.getUTCDate()), weekend: zoom === "day" && (dow === 0 || dow === 6) });
    }
  }

  const arrows: { x1: number; y1: number; x2: number; y2: number; late: boolean }[] = [];
  rows.forEach((r, i) => {
    for (const dep of r.task.depends_on) {
      const j = index.get(dep);
      if (j == null) continue;
      const from = rows[j];
      if (from.end == null || r.start == null) continue;
      arrows.push({
        x1: x(from.end + 1),
        y1: j * ROW + ROW / 2,
        x2: x(r.start),
        y2: i * ROW + ROW / 2,
        late: r.start <= from.end,
      });
    }
  });

  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{t("gantt.unscheduled")}</p>
        <div className="flex gap-1">
          {(["day", "week"] as const).map((z) => (
            <Button key={z} size="sm" variant={zoom === z ? "secondary" : "ghost"} onClick={() => setZoom(z)}>
              {t(z === "day" ? "gantt.zoomDay" : "gantt.zoomWeek")}
            </Button>
          ))}
        </div>
      </div>
      <div className="flex overflow-hidden rounded-lg border">
        {/* Task list */}
        <div className="w-40 shrink-0 border-r bg-background sm:w-80">
          <div className="flex items-end border-b px-3 pb-1.5 text-xs font-medium text-muted-foreground" style={{ height: HEADER }}>
            {t("task")}
          </div>
          {rows.map((r) => (
            <button
              key={r.task.id}
              type="button"
              onClick={() => onOpen(r.task)}
              className="flex w-full items-center gap-2 border-b px-3 text-left text-sm hover:bg-muted/50"
              style={{ height: ROW, paddingLeft: 12 + r.depth * 16 }}
            >
              <span className="text-xs text-muted-foreground tabular-nums">#{r.task.number}</span>
              <span className={cn("min-w-0 flex-1 truncate", r.isPhase && "font-semibold", r.task.status === "done" && "text-muted-foreground line-through")}>
                {titleOf(r.task)}
              </span>
              {r.task.kind !== "development" && (
                <span className="hidden sm:inline">
                  <TaskKindBadge kind={r.task.kind} />
                </span>
              )}
              <span className="hidden sm:inline">
                <DueLabel task={r.task} />
              </span>
            </button>
          ))}
        </div>
        {/* Timeline */}
        <div ref={scroller} className="min-w-0 flex-1 overflow-x-auto">
          <div className="relative" style={{ width, height: HEADER + rows.length * ROW }}>
            <div className="sticky top-0 border-b bg-background" style={{ height: HEADER }}>
              {months.map((m) => (
                <span key={m.left} className="absolute top-1 text-xs font-medium whitespace-nowrap" style={{ left: m.left + 4 }}>
                  {m.label}
                </span>
              ))}
              {ticks.map((tk) => (
                <span
                  key={tk.left}
                  className={cn("absolute bottom-1 text-center text-[10px] text-muted-foreground tabular-nums", tk.weekend && "text-red-500/70")}
                  style={{ left: tk.left, width: dayWidth }}
                >
                  {tk.label}
                </span>
              ))}
            </div>
            <div className="absolute inset-x-0" style={{ top: HEADER }}>
              {zoom === "day" &&
                ticks
                  .filter((tk) => tk.weekend)
                  .map((tk) => (
                    <div key={tk.left} className="absolute bg-muted/50" style={{ left: tk.left, width: dayWidth, top: 0, height: rows.length * ROW }} />
                  ))}
              {rows.map((r, i) => (
                <div key={r.task.id} className="absolute inset-x-0 border-b" style={{ top: i * ROW, height: ROW }}>
                  {r.start != null && r.end != null && <Bar row={r} left={x(r.start)} width={(r.end - r.start + 1) * dayWidth} onOpen={onOpen} title={titleOf(r.task)} />}
                </div>
              ))}
              <svg className="pointer-events-none absolute inset-0 overflow-visible" width={width} height={rows.length * ROW} aria-hidden="true">
                <defs>
                  <marker id="gantt-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M0,0 L8,4 L0,8 z" className="fill-muted-foreground" />
                  </marker>
                </defs>
                {arrows.map((a, k) => {
                  const mid = Math.max(a.x1 + 6, Math.min(a.x2 - 6, (a.x1 + a.x2) / 2));
                  return (
                    <path
                      key={k}
                      d={`M${a.x1},${a.y1} H${mid} V${a.y2} H${a.x2}`}
                      fill="none"
                      strokeWidth={1.25}
                      className={a.late ? "stroke-red-500" : "stroke-muted-foreground"}
                      markerEnd="url(#gantt-arrow)"
                    />
                  );
                })}
              </svg>
              <div className="absolute w-px bg-red-500" style={{ left: x(today) + dayWidth / 2, top: -8, height: rows.length * ROW + 8 }} title={t("gantt.today")} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Bar({ row, left, width, onOpen, title }: { row: Row; left: number; width: number; onOpen: (t: Task) => void; title: string }) {
  const task = row.task;
  if (task.is_milestone) {
    return (
      <button
        type="button"
        onClick={() => onOpen(task)}
        title={title}
        className={cn("absolute top-1/2 size-3.5 -translate-y-1/2 rotate-45 rounded-[2px]", task.status === "done" ? "bg-emerald-500" : "bg-foreground")}
        style={{ left: left + width / 2 - 7 }}
      />
    );
  }
  if (row.isPhase) {
    return (
      <button
        type="button"
        onClick={() => onOpen(task)}
        title={title}
        className="absolute top-1/2 h-2 -translate-y-1/2 rounded-sm bg-foreground/70"
        style={{ left, width: Math.max(width, 6) }}
      />
    );
  }
  const color =
    task.status === "done"
      ? "bg-emerald-500/70"
      : task.overdue
        ? "bg-red-500/80"
        : task.kind === "security"
          ? "bg-red-400/70"
          : "bg-sky-500/70";
  return (
    <button
      type="button"
      onClick={() => onOpen(task)}
      title={title}
      className={cn("absolute top-1/2 flex h-5 -translate-y-1/2 items-center overflow-hidden rounded text-left", color)}
      style={{ left, width: Math.max(width, 8) }}
    >
      <span className="absolute inset-y-0 left-0 bg-black/20" style={{ width: `${task.progress}%` }} />
      <span className="relative px-1.5 text-[11px] font-medium whitespace-nowrap text-white">{width > 60 ? title : ""}</span>
    </button>
  );
}
