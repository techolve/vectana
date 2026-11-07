import { defineTool, id } from "./define.ts";

export const repoTools = [
  defineTool({
    name: "list_repo_links",
    title: "List linked repositories",
    description:
      "GitHub / GitLab repositories linked to a project: default branch, whether issues sync, the last import and the last error.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/repo-links`),
  }),
  defineTool({
    name: "import_from_repo",
    title: "Import dependency files from a repository",
    description:
      "Read the lockfiles and SBOMs on the default branch of a linked repository now (it also happens on push and daily). Returns each file's result. Project managers only.",
    write: true,
    idempotent: true,
    input: { repo_link_id: id("Repository link (from list_repo_links)") },
    run: ({ repo_link_id }, c) => c.post(`/api/repo-links/${repo_link_id}/import`),
  }),
  defineTool({
    name: "sync_repo_issues",
    title: "Import issues from a repository",
    description:
      "Bring the open issues and milestones of a linked repository in as tasks and sprints (catching up on missed webhooks). Project managers only.",
    write: true,
    idempotent: true,
    input: { repo_link_id: id("Repository link (from list_repo_links)") },
    run: ({ repo_link_id }, c) => c.post(`/api/repo-links/${repo_link_id}/sync`),
  }),
];
