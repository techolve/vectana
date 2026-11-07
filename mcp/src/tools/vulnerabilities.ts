import { z } from "zod";

import { apiEnum, date, defineTool, given, id, type Schemas } from "./define.ts";

export const severity = apiEnum<Schemas["Severity"]>()([
  "UNKNOWN",
  "LOW",
  "MEDIUM",
  "HIGH",
  "CRITICAL",
]);
export const matchStatus = apiEnum<Schemas["MatchStatus"]>()(["open", "ack", "ignored"]).describe(
  "open = not handled yet, ack = acknowledged / being handled, ignored = not affected or accepted",
);

export const vulnerabilityTools = [
  defineTool({
    name: "list_vulnerabilities",
    title: "List vulnerabilities",
    description:
      "Vulnerability hits (a vulnerable package version in a project) the user can see, most severe first. Each hit has its triage state (status, assignee, due_date, sla_due_date) and the recommended upgrade version.",
    input: {
      project_id: id("Project").optional(),
      status: z
        .array(apiEnum<Schemas["MatchStatus"]>()(["open", "ack", "ignored"]))
        .default(["open"])
        .describe("Statuses to include; empty for all. Default: open"),
      severity: severity.optional().describe("Only this severity"),
      assignee: z.string().optional().describe('"me", "none" (unassigned) or a user ID'),
      overdue: z.boolean().default(false).describe("Only unresolved hits past their due date"),
      limit: z.number().int().min(1).max(1000).default(100),
    },
    run: ({ status, ...rest }, c) =>
      c.get("/api/vulnerabilities", { ...rest, status: status.join(",") }),
  }),
  defineTool({
    name: "get_vulnerability",
    title: "Vulnerability details",
    description: "One vulnerability hit with its advisory details, comments and change history.",
    input: { match_id: id("Vulnerability hit") },
    run: ({ match_id }, c) => c.get(`/api/vulnerabilities/${match_id}`),
  }),
  defineTool({
    name: "update_vulnerability",
    title: "Triage a vulnerability",
    description:
      "Change a vulnerability hit's status, assignee or due date. Only the fields you pass change; pass null to clear assignee_id or due_date. Leave a comment with comment_vulnerability to explain why.",
    write: true,
    idempotent: true,
    input: {
      match_id: id("Vulnerability hit"),
      status: matchStatus.optional(),
      assignee_id: id("Assignee user").nullable().optional(),
      due_date: date("Due date").nullable().optional(),
    },
    run: ({ match_id, ...body }, c) => c.patch(`/api/vulnerabilities/${match_id}`, given(body)),
  }),
  defineTool({
    name: "comment_vulnerability",
    title: "Comment on a vulnerability",
    description: "Add a comment to a vulnerability hit, e.g. the reason for a triage decision.",
    write: true,
    input: { match_id: id("Vulnerability hit"), body: z.string().min(1).max(5000) },
    run: ({ match_id, body }, c) => c.post(`/api/vulnerabilities/${match_id}/comments`, { body }),
  }),
];
