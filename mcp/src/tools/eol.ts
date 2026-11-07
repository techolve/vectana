import { z } from "zod";

import { apiEnum, defineTool, id, type Schemas } from "./define.ts";

const eolStatus = apiEnum<Schemas["EolStatus"]>()(["supported", "approaching", "eol", "unknown"]);

export const eolTools = [
  defineTool({
    name: "list_eol",
    title: "List EOL findings",
    description:
      "End-of-life status of the runtimes, frameworks and packages in the user's projects (from endoflife.date), soonest first.",
    input: {
      project_id: id("Project").optional(),
      status: z
        .array(eolStatus)
        .optional()
        .describe("approaching = EOL within the warning window, eol = already past"),
      limit: z.number().int().min(1).max(1000).default(100),
    },
    run: (args, c) => c.get("/api/eol", args),
  }),
  defineTool({
    name: "list_runtimes",
    title: "List runtimes",
    description: "Runtimes (e.g. nodejs 22, python 3.12) registered in a project for EOL tracking.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/runtimes`),
  }),
  defineTool({
    name: "search_eol_products",
    title: "Search EOL products",
    description: "Find endoflife.date product names to use with add_runtime.",
    input: { q: z.string().min(1) },
    run: ({ q }, c) => c.get("/api/eol/products", { q }),
  }),
  defineTool({
    name: "add_runtime",
    title: "Add a runtime",
    description: "Register a runtime version in a project for EOL tracking.",
    write: true,
    input: {
      project_id: id("Project"),
      product: z.string().describe("endoflife.date product, e.g. nodejs, python, postgresql"),
      version: z.string().describe("Version or cycle, e.g. 22 or 3.12.4"),
    },
    run: ({ project_id, ...body }, c) => c.post(`/api/projects/${project_id}/runtimes`, body),
  }),
];
