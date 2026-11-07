import { z } from "zod";

import { apiEnum, date, defineTool, given, id, type Schemas } from "./define.ts";

const estimateKind = apiEnum<Schemas["EstimateKind"]>()([
  "initial",
  "additional",
  "maintenance",
  "other",
]);
const estimateStatus = apiEnum<Schemas["EstimateStatus"]>()([
  "draft",
  "submitted",
  "won",
  "lost",
]).describe("Setting won moves a deal to won");
const billing = apiEnum<Schemas["Billing"]>()(["one_time", "monthly"]);

const line = z.object({
  label: z.string().min(1).describe("Work item or role, e.g. 基本設計"),
  user_id: id("Assigned user").nullable().optional(),
  days: z.number().min(0).describe("Effort in person-days (人日)"),
  unit_cost: z
    .number()
    .int()
    .min(0)
    .nullable()
    .optional()
    .describe("Cost per person-day (JPY). Default: the user's unit cost"),
});

const estimateFields = {
  kind: estimateKind.optional(),
  status: estimateStatus.optional(),
  billing: billing.optional(),
  amount: z.number().int().min(0).nullable().optional().describe("Quoted price (JPY)"),
  effort_days: z.number().min(0).nullable().optional().describe("Total effort in person-days"),
  issued_on: date("Issue date").nullable().optional(),
  due_on: date("Delivery date").nullable().optional(),
  valid_until: date("Valid until").nullable().optional(),
  decided_on: date("Decision date").nullable().optional(),
  lost_reason: z.string().nullable().optional(),
  competitor: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
};

export const estimateTools = [
  defineTool({
    name: "list_estimates",
    title: "List estimates",
    description:
      "Estimates of a project or deal. Amounts are hidden from partner users; unit costs only show to admins, sales and accounting.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/estimates`),
  }),
  defineTool({
    name: "get_estimate",
    title: "Estimate details",
    description: "One estimate with its lines (effort and cost per work item).",
    input: { estimate_id: id("Estimate") },
    run: ({ estimate_id }, c) => c.get(`/api/estimates/${estimate_id}`),
  }),
  defineTool({
    name: "create_estimate",
    title: "Create an estimate",
    description:
      "Add an estimate to a project or deal. Lines carry effort in person-days; their cost is snapshotted from each user's unit cost unless given.",
    write: true,
    input: {
      project_id: id("Project"),
      title: z.string().min(1).max(200),
      lines: z.array(line).default([]),
      ...estimateFields,
    },
    run: ({ project_id, ...body }, c) =>
      c.post(`/api/projects/${project_id}/estimates`, given(body)),
  }),
  defineTool({
    name: "update_estimate",
    title: "Update an estimate",
    description:
      "Change an estimate. Only the fields you pass change; null clears a field. Passing lines replaces all lines.",
    write: true,
    idempotent: true,
    input: {
      estimate_id: id("Estimate"),
      title: z.string().min(1).max(200).optional(),
      lines: z.array(line).optional(),
      ...estimateFields,
    },
    run: ({ estimate_id, ...body }, c) => c.patch(`/api/estimates/${estimate_id}`, given(body)),
  }),
];
