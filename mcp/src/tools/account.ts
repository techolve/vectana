import { z } from "zod";

import { defineTool } from "./define.ts";

export const accountTools = [
  defineTool({
    name: "whoami",
    title: "Current user",
    description:
      "The user this server acts as: email, company, roles (group_admin, company_admin, sales, accounting, pmo) and what they may do (can_sell, can_see_customers, is_partner).",
    input: {},
    run: (_args, c) => c.get("/api/auth/me"),
  }),
  defineTool({
    name: "search_users",
    title: "Search users",
    description:
      "Find users by name or email, e.g. to get an assignee_id for a vulnerability or a manager_id for a project.",
    input: { q: z.string().default("").describe("Part of a name or email; empty lists everyone") },
    run: ({ q }, c) => c.get("/api/users/directory", { q }),
  }),
];
