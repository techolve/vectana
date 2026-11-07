import { z } from "zod";

import { apiEnum, date, defineTool, given, id, type Schemas } from "./define.ts";

const projectStatus = apiEnum<Schemas["ProjectStatus"]>()([
  "inquiry",
  "proposal",
  "negotiation",
  "won",
  "development",
  "maintenance",
  "on_hold",
  "lost",
]).describe(
  "Deal stages: inquiry → proposal → negotiation → won (or lost / on_hold). Delivery: development, maintenance. Entering won/development/maintenance records the order date.",
);
const projectMethod = apiEnum<Schemas["ProjectMethod"]>()(["waterfall", "scrum"]);
const memberRole = apiEnum<Schemas["ProjectRole"]>()(["owner", "member", "viewer"]);

// Fields shared by create and update. All optional; null clears on update.
const projectFields = {
  description: z.string().nullable().optional(),
  department_id: id("Department").nullable().optional(),
  status: projectStatus.optional(),
  method: projectMethod.optional().describe("waterfall = Gantt chart, scrum = sprint board"),
  customer_id: id("Customer").nullable().optional(),
  sales_owner_id: id("Sales owner user").nullable().optional(),
  manager_id: id("Project manager user").nullable().optional(),
  starts_on: date("Start date").nullable().optional(),
  ends_on: date("End date").nullable().optional(),
  expected_amount: z.number().int().min(0).nullable().optional().describe("Expected deal amount (JPY)"),
  probability: z.number().int().min(0).max(100).nullable().optional().describe("Win probability (%)"),
  next_action: z.string().max(200).nullable().optional(),
  next_action_on: date("Next action date").nullable().optional(),
};

export const projectTools = [
  defineTool({
    name: "list_projects",
    title: "List projects",
    description:
      "Projects and deals the user can see, with status, customer, package and open vulnerability counts.",
    input: { customer_id: id("Customer").optional() },
    run: (args, c) => c.get("/api/projects", args),
  }),
  defineTool({
    name: "get_project",
    title: "Project details",
    description: "One project: status, schedule, customer, people, deal figures and the user's role.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}`),
  }),
  defineTool({
    name: "list_project_members",
    title: "List project members",
    description: "Users assigned to a project and their roles (owner, member, viewer).",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/members`),
  }),
  defineTool({
    name: "create_project",
    title: "Create a project",
    description:
      "Create a project or a deal. Internal projects start at development or maintenance; deals (sales only) start at inquiry. The user becomes its owner.",
    write: true,
    input: {
      name: z.string().min(1).max(200),
      company_id: id("Company").optional().describe("Default: the user's company"),
      ...projectFields,
    },
    run: (args, c) => c.post("/api/projects", given(args)),
  }),
  defineTool({
    name: "update_project",
    title: "Update a project",
    description:
      "Change a project's fields or move a deal through its stages. Only the fields you pass change; null clears a field.",
    write: true,
    idempotent: true,
    input: {
      project_id: id("Project"),
      name: z.string().min(1).max(200).optional(),
      ordered_on: date("Order date").nullable().optional(),
      lost_reason: z.string().nullable().optional(),
      competitor: z.string().max(200).nullable().optional(),
      ...projectFields,
    },
    run: ({ project_id, ...body }, c) => c.patch(`/api/projects/${project_id}`, given(body)),
  }),
  defineTool({
    name: "add_project_member",
    title: "Assign a member",
    description: "Assign a user to a project (find the user with search_users). Needs owner access.",
    write: true,
    input: {
      project_id: id("Project"),
      user_id: id("User"),
      role: memberRole.default("member"),
    },
    run: ({ project_id, ...body }, c) => c.post(`/api/projects/${project_id}/members`, body),
  }),
];
