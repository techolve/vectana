import { z } from "zod";

import { apiEnum, date, defineTool, given, id, type Schemas } from "./define.ts";

const sprintStatus = apiEnum<Schemas["SprintStatus"]>()(["planned", "active", "closed"]);
const doneItem = z.object({ text: z.string().min(1).max(300), done: z.boolean().default(false) });

export const sprintTools = [
  defineTool({
    name: "list_sprints",
    title: "List sprints",
    description: "Sprints of a scrum project with committed and completed points.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/sprints`),
  }),
  defineTool({
    name: "get_burndown",
    title: "Sprint burndown",
    description: "Ideal and remaining points (or tasks) per day of a sprint.",
    input: { sprint_id: id("Sprint") },
    run: ({ sprint_id }, c) => c.get(`/api/sprints/${sprint_id}/burndown`),
  }),
  defineTool({
    name: "get_velocity",
    title: "Velocity",
    description: "Committed and completed points of each sprint of a project.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/velocity`),
  }),
  defineTool({
    name: "create_sprint",
    title: "Create a sprint",
    description: "Add a sprint to a scrum project. Move tasks into it with update_task (sprint_id).",
    write: true,
    input: {
      project_id: id("Project"),
      name: z.string().min(1).max(100),
      goal: z.string().nullable().optional(),
      starts_on: date("Start date"),
      ends_on: date("End date"),
      status: sprintStatus.optional(),
      definition_of_done: z.array(doneItem).optional(),
    },
    run: ({ project_id, ...body }, c) =>
      c.post(`/api/projects/${project_id}/sprints`, given(body)),
  }),
  defineTool({
    name: "update_sprint",
    title: "Update a sprint",
    description:
      "Change a sprint, e.g. start it (status active) or close it. Only the fields you pass change.",
    write: true,
    idempotent: true,
    input: {
      sprint_id: id("Sprint"),
      name: z.string().min(1).max(100).optional(),
      goal: z.string().nullable().optional(),
      starts_on: date("Start date").optional(),
      ends_on: date("End date").optional(),
      status: sprintStatus.optional(),
      definition_of_done: z.array(doneItem).optional(),
    },
    run: ({ sprint_id, ...body }, c) => c.patch(`/api/sprints/${sprint_id}`, given(body)),
  }),
];
