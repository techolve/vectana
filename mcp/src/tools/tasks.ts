import { z } from "zod";

import { apiEnum, date, defineTool, given, id, type Schemas } from "./define.ts";

const taskKind = apiEnum<Schemas["TaskKind"]>()(["development", "security", "other"]).describe(
  "security = upgrade a package or runtime to fix vulnerabilities / EOL",
);
const taskStatus = apiEnum<Schemas["TaskStatus"]>()(["todo", "in_progress", "done"]);
const taskPriority = apiEnum<Schemas["TaskPriority"]>()(["high", "medium", "low"]);

// Fields shared by create and update. All optional; null clears on update.
const taskFields = {
  kind: taskKind.optional(),
  description: z.string().nullable().optional(),
  status: taskStatus.optional(),
  priority: taskPriority.nullable().optional(),
  assignee_id: id("Assignee user").nullable().optional(),
  start_date: date("Start date").nullable().optional(),
  due_date: date("Due date").nullable().optional(),
  parent_id: id("Parent task").nullable().optional(),
  is_milestone: z.boolean().optional(),
  progress: z.number().int().min(0).max(100).optional().describe("Percent done (Gantt)"),
  depends_on: z.array(id("Task")).optional().describe("Tasks that must finish first (Gantt)"),
  sprint_id: id("Sprint").nullable().optional().describe("null = backlog"),
  points: z.number().min(0).nullable().optional().describe("Story points (scrum)"),
  estimate_hours: z.number().min(0).nullable().optional(),
};

export const taskTools = [
  defineTool({
    name: "list_my_tasks",
    title: "List my tasks",
    description:
      "Tasks across all projects, overdue and nearest due first: assigned to the user (mine), in the projects they belong to (team), or unassigned there.",
    input: {
      scope: z.enum(["mine", "team", "unassigned"]).default("mine"),
      open: z.boolean().default(true).describe("Only tasks that are not done"),
      limit: z.number().int().min(1).max(500).default(100),
    },
    run: (args, c) => c.get("/api/tasks", args),
  }),
  defineTool({
    name: "list_project_tasks",
    title: "List project tasks",
    description:
      "Tasks of one project in board / Gantt order. Security tasks include the package, installed versions and the recommended upgrade.",
    input: {
      project_id: id("Project"),
      kind: taskKind.optional(),
      open: z.boolean().default(false).describe("Only tasks that are not done"),
      sprint_id: z.string().optional().describe('A sprint ID, or "none" for the backlog'),
    },
    run: ({ project_id, ...query }, c) => c.get(`/api/projects/${project_id}/tasks`, query),
  }),
  defineTool({
    name: "get_task",
    title: "Task details",
    description: "One task, with the vulnerabilities and EOL findings a security task covers.",
    input: { task_id: id("Task") },
    run: ({ task_id }, c) => c.get(`/api/tasks/${task_id}`),
  }),
  defineTool({
    name: "create_task",
    title: "Create a task",
    description:
      "Add a development or other task to a project. For vulnerabilities use create_security_task instead.",
    write: true,
    input: { project_id: id("Project"), title: z.string().min(1).max(300), ...taskFields },
    run: ({ project_id, ...body }, c) => c.post(`/api/projects/${project_id}/tasks`, given(body)),
  }),
  defineTool({
    name: "update_task",
    title: "Update a task",
    description:
      "Change a task: status, priority, assignee, dates, sprint, points and so on. Only the fields you pass change; null clears a field. Title, status, priority, assignee and sprint also reach a linked GitHub / GitLab issue.",
    write: true,
    idempotent: true,
    input: { task_id: id("Task"), title: z.string().min(1).max(300).optional(), ...taskFields },
    run: ({ task_id, ...body }, c) => c.patch(`/api/tasks/${task_id}`, given(body)),
  }),
  defineTool({
    name: "list_security_candidates",
    title: "Vulnerabilities without a task",
    description:
      "Packages and runtimes of a project whose vulnerabilities or EOL have no security task yet, with the recommended upgrade.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/security/candidates`),
  }),
  defineTool({
    name: "create_security_task",
    title: "Create a security task",
    description:
      "Turn a candidate from list_security_candidates into a security task (one task per package upgrade). If the package already has an open task, its findings are added there.",
    write: true,
    input: {
      project_id: id("Project"),
      subject: z.enum(["package", "runtime"]),
      ecosystem: z.string().describe("As in the candidate"),
      name: z.string().describe("As in the candidate"),
    },
    run: ({ project_id, ...body }, c) =>
      c.post(`/api/projects/${project_id}/security/tasks`, body),
  }),
];
