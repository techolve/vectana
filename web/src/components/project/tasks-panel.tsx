"use client";

import { useState } from "react";
import { PlusIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Project, Sprint, Task } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Gantt } from "@/components/task/gantt";
import { ScrumBoard } from "@/components/task/scrum";
import { TaskDialog, type TaskDraft } from "@/components/task/task-common";
import { TaskList } from "@/components/task/task-list";

type View = "gantt" | "board" | "list";

/** The project's tasks: Gantt for waterfall, board for scrum, a simple list in maintenance. */
export function TasksPanel({ project, canWrite }: { project: Project; canWrite: boolean }) {
  const t = useTranslations();
  const preferred: View =
    project.status === "maintenance" ? "list" : project.method === "scrum" ? "board" : "gantt";
  const [view, setView] = useState<View>(preferred);
  const { data: tasks, reload } = useApi<Task[]>(`/projects/${project.id}/tasks`);
  const { data: sprints, reload: reloadSprints } = useApi<Sprint[]>(`/projects/${project.id}/sprints`);
  const [open, setOpen] = useState<Task | TaskDraft | null>(null);
  const refresh = () => {
    reload();
    reloadSprints();
  };

  if (!tasks || !sprints) return null;
  const editing = open && "id" in open ? (open as Task) : null;
  const scrum = view === "board" || sprints.length > 0;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-lg border p-0.5">
          {(["gantt", "board", "list"] as const).map((v) => (
            <Button key={v} size="sm" variant={view === v ? "secondary" : "ghost"} onClick={() => setView(v)}>
              {t(`tasks.view.${v}`)}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          {project.status === "maintenance"
            ? t("tasks.maintenanceHint", { threshold: project.security_threshold })
            : t("tasks.methodHint", { method: t(`labels.method.${project.method}`) })}
        </p>
        {canWrite && view !== "board" && (
          <Button className="ml-auto" onClick={() => setOpen({})}>
            <PlusIcon /> {t("tasks.add")}
          </Button>
        )}
      </div>
      {view === "gantt" && <Gantt tasks={tasks} onOpen={setOpen} />}
      {view === "list" && <TaskList tasks={tasks} onOpen={setOpen} />}
      {view === "board" && (
        <ScrumBoard
          projectId={project.id}
          tasks={tasks}
          sprints={sprints}
          canWrite={canWrite}
          onOpen={setOpen}
          onAdd={setOpen}
          onChanged={refresh}
        />
      )}
      {open && (
        <TaskDialog
          key={editing?.id ?? "new"}
          projectId={project.id}
          task={editing}
          draft={editing ? undefined : (open as TaskDraft)}
          tasks={tasks}
          sprints={scrum ? sprints : undefined}
          canWrite={canWrite}
          onClose={() => setOpen(null)}
          onSaved={() => {
            setOpen(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}
