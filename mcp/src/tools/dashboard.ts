import { defineTool, id } from "./define.ts";

export const dashboardTools = [
  defineTool({
    name: "get_dashboard",
    title: "Dashboard",
    description:
      "The user's dashboard: open vulnerabilities by severity, overdue and assigned-to-me counts, EOL warnings and the projects that need attention.",
    input: {},
    run: (_args, c) => c.get("/api/dashboard"),
  }),
  defineTool({
    name: "get_org_dashboard",
    title: "Organization dashboard",
    description:
      "Vulnerability and EOL figures per company and department (for admins and department heads).",
    input: { company_id: id("Company").optional() },
    run: ({ company_id }, c) => c.get("/api/org-dashboard", { company_id }),
  }),
];

