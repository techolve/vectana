import { z } from "zod";

import { apiEnum, date, defineTool, given, id, type Schemas } from "./define.ts";
import type { VectanaClient } from "../client.ts";

type Timesheet = Schemas["TimesheetOut"];

const hours = z
  .array(z.number().min(0).max(24).nullable())
  .length(7)
  .describe("Hours Monday..Sunday; null or 0 = nothing that day");

const row = z.object({
  project_id: id("Project").nullable().optional(),
  task_id: id("Task (its project is implied)").nullable().optional(),
  label: z.string().max(200).nullable().optional().describe("Work outside projects, e.g. 社内会議"),
  hours,
});

const activityKind = apiEnum<Schemas["ActivityKind"]>()(["meeting", "phone", "email"]);
const invoiceStatus = apiEnum<Schemas["InvoiceStatus"]>()(["planned", "invoiced", "paid"]);

function weekQuery(week: string | undefined, user_id: string | undefined) {
  return { ...(week ? { week } : {}), ...(user_id ? { user_id } : {}) };
}

/** Set one day's hours on one row of the week, keeping everything else. */
async function logTime(
  c: VectanaClient,
  args: {
    work_date: string;
    hours: number;
    project_id?: string;
    task_id?: string;
    label?: string;
    user_id?: string;
  },
): Promise<Timesheet> {
  const sheet = await c.get<Timesheet>("/api/timesheet", weekQuery(args.work_date, args.user_id));
  const day = sheet.days.indexOf(args.work_date);
  const rows = sheet.rows.map((r) => ({
    project_id: r.project_id,
    task_id: r.task_id,
    label: r.label,
    hours: [...r.hours],
  }));
  let target = rows.find((r) =>
    args.task_id
      ? r.task_id === args.task_id
      : args.project_id
        ? r.project_id === args.project_id && !r.task_id
        : !r.project_id && r.label === args.label?.trim(),
  );
  if (!target) {
    target = {
      project_id: args.project_id ?? null,
      task_id: args.task_id ?? null,
      label: args.task_id || args.project_id ? null : (args.label ?? null),
      hours: Array<number | null>(7).fill(null),
    };
    rows.push(target);
  }
  target.hours[day] = args.hours || null;
  return c.put<Timesheet>("/api/timesheet", {
    week_start: sheet.week_start,
    user_id: args.user_id ?? null,
    rows,
  });
}

export const workTools = [
  defineTool({
    name: "get_timesheet",
    title: "Timesheet of a week",
    description:
      "Hours per task and day for one week (Monday start), with each task's estimate and actual hours so far. Defaults to your own current week.",
    input: {
      week: date("Any day of the week").optional(),
      user_id: id("Person (admins and department heads)").optional(),
    },
    run: ({ week, user_id }, c) => c.get("/api/timesheet", weekQuery(week, user_id)),
  }),
  defineTool({
    name: "log_time",
    title: "Log hours",
    description:
      "Set the hours worked on one day for a task, a project (no task), or a label outside projects. Other days and rows of the week are kept. hours 0 clears the day.",
    write: true,
    idempotent: true,
    input: {
      work_date: date("Day worked"),
      hours: z.number().min(0).max(24),
      task_id: id("Task").optional(),
      project_id: id("Project (when no task)").optional(),
      label: z.string().max(200).optional().describe("Work outside projects"),
      user_id: id("Person (company admins only)").optional(),
    },
    run: (args, c) => {
      if (!args.task_id && !args.project_id && !args.label?.trim()) {
        throw new Error("Give task_id, project_id or label");
      }
      return logTime(c, args);
    },
  }),
  defineTool({
    name: "save_timesheet",
    title: "Replace a week's timesheet",
    description:
      "Replace the whole week with the rows given (rows left out are removed). Use log_time to change a single day.",
    write: true,
    idempotent: true,
    input: {
      week_start: date("Any day of the week"),
      rows: z.array(row).max(200),
      user_id: id("Person (company admins only)").optional(),
    },
    run: (body, c) => c.put("/api/timesheet", given(body)),
  }),
  defineTool({
    name: "submit_timesheet",
    title: "Submit a week",
    description: "Mark the week's timesheet as submitted (週を提出).",
    write: true,
    idempotent: true,
    input: { week: date("Any day of the week"), user_id: id("Person").optional() },
    run: ({ week, user_id }, c) =>
      c.post(`/api/timesheet/submit?${new URLSearchParams(weekQuery(week, user_id))}`),
  }),
  defineTool({
    name: "get_project_actuals",
    title: "Estimate vs actual",
    description:
      "Won estimates' effort against the hours entered: overall, per phase and per person (person-days of 8 hours). Actual cost only for those who see unit costs. Not for partner users.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/actuals`),
  }),
  defineTool({
    name: "list_activities",
    title: "List deal notes",
    description: "商談メモ of a project: meetings, calls and emails, newest first, with the task of each next action.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/activities`),
  }),
  defineTool({
    name: "add_activity",
    title: "Add a deal note",
    description:
      "Record a meeting, call or email. A next action becomes a task for its assignee (default: you) and the project's next action.",
    write: true,
    input: {
      project_id: id("Project"),
      kind: activityKind.default("meeting"),
      occurred_on: date("Date"),
      body: z.string().min(1).describe("What was discussed"),
      participants: z.string().max(300).optional(),
      next_action: z.string().max(200).optional(),
      next_action_assignee_id: id("Assignee of the next action").optional(),
      next_action_due: date("Due date of the next action").optional(),
    },
    run: ({ project_id, ...body }, c) =>
      c.post(`/api/projects/${project_id}/activities`, given(body)),
  }),
  defineTool({
    name: "update_activity",
    title: "Update a deal note",
    description: "Change a note. The next action is edited on its task (update_task).",
    write: true,
    idempotent: true,
    input: {
      activity_id: id("Deal note"),
      kind: activityKind.optional(),
      occurred_on: date("Date").optional(),
      participants: z.string().max(300).nullable().optional(),
      body: z.string().min(1).optional(),
    },
    run: ({ activity_id, ...body }, c) => c.patch(`/api/activities/${activity_id}`, given(body)),
  }),
  defineTool({
    name: "list_project_invoices",
    title: "Project invoices",
    description: "Invoices planned from the project's won estimates, with their status.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/invoices`),
  }),
  defineTool({
    name: "list_invoices",
    title: "List invoices (accounting)",
    description:
      "Invoices across projects for accounting and admins. With a month: that month's planned and paid invoices plus every one still awaiting payment.",
    input: {
      month: z
        .string()
        .regex(/^\d{4}-\d{2}$/)
        .optional()
        .describe("YYYY-MM"),
      status: z.enum(["planned", "invoiced", "paid", "overdue"]).optional(),
      company_id: id("Company").optional(),
    },
    run: (q, c) => c.get("/api/invoices", given(q) as Record<string, string>),
  }),
  defineTool({
    name: "plan_invoices",
    title: "Plan invoices of an estimate",
    description:
      "Set the installments of a won estimate (e.g. 30% upfront, 70% on delivery, or one per month for maintenance). Replaces the planned ones; invoiced and paid ones stay. Sales and admins.",
    write: true,
    idempotent: true,
    input: {
      estimate_id: id("Won estimate"),
      items: z
        .array(
          z.object({
            label: z.string().min(1).max(200).describe("e.g. 着手金, 2026年12月分"),
            planned_on: date("Planned invoice date"),
            amount: z.number().int().min(0).describe("JPY excluding tax"),
          }),
        )
        .max(120),
    },
    run: ({ estimate_id, items }, c) => c.put(`/api/estimates/${estimate_id}/invoices`, { items }),
  }),
  defineTool({
    name: "update_invoice",
    title: "Record or change an invoice",
    description:
      "Accounting and admins: mark invoiced (due date defaults to the end of the next month) or paid, or set it back. Sales: change label, date or amount while still planned.",
    write: true,
    idempotent: true,
    input: {
      invoice_id: id("Invoice"),
      status: invoiceStatus.optional(),
      invoiced_on: date("Invoice date").optional(),
      due_on: date("Payment due").optional(),
      paid_on: date("Paid on").optional(),
      label: z.string().min(1).max(200).optional(),
      planned_on: date("Planned date").optional(),
      amount: z.number().int().min(0).optional(),
    },
    run: ({ invoice_id, ...body }, c) => c.patch(`/api/invoices/${invoice_id}`, given(body)),
  }),
];
