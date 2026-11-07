import { readFile } from "node:fs/promises";
import { basename } from "node:path";

import { z } from "zod";

import { defineTool, id } from "./define.ts";

export const packageTools = [
  defineTool({
    name: "list_packages",
    title: "List packages",
    description:
      "Packages registered in a project, with their open vulnerability counts and the recommended upgrade.",
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.get(`/api/projects/${project_id}/packages`),
  }),
  defineTool({
    name: "add_package",
    title: "Add a package",
    description: "Register one package version in a project by hand.",
    write: true,
    input: {
      project_id: id("Project"),
      ecosystem: z.string().describe("OSV ecosystem, e.g. npm, PyPI, Go, Maven, crates.io, Packagist"),
      name: z.string().min(1),
      version: z.string().min(1),
    },
    run: ({ project_id, ...body }, c) => c.post(`/api/projects/${project_id}/packages`, body),
  }),
  defineTool({
    name: "import_dependencies",
    title: "Import a lockfile or SBOM",
    description:
      "Sync a project's packages from a lockfile (package-lock.json, pnpm-lock.yaml, uv.lock, poetry.lock, requirements*.txt, pubspec.lock, go.mod, go.sum, composer.lock, Cargo.lock, gradle.lockfile), an SBOM (CycloneDX JSON/XML, SPDX JSON/tag-value), or runtimes from mise.toml / .tool-versions. Re-importing the same source replaces what it added before. Give either a local file path or the file's content with its filename. A scan runs afterwards.",
    write: true,
    idempotent: true,
    input: {
      project_id: id("Project"),
      path: z.string().optional().describe("Path of the file on this machine"),
      content: z.string().optional().describe("The file's content, when not giving path"),
      filename: z
        .string()
        .optional()
        .describe("File name, which tells the format (needed with content, e.g. package-lock.json)"),
      source: z
        .string()
        .max(200)
        .optional()
        .describe("Name of this source, e.g. frontend/package-lock.json. Default: the file name"),
    },
    run: async ({ project_id, path, content, filename, source }, c) => {
      let data: string | Uint8Array<ArrayBuffer>;
      if (path) {
        data = new Uint8Array(await readFile(path));
        filename ??= basename(path);
      } else if (content !== undefined && filename) {
        data = content;
      } else {
        throw new Error("Give path, or content together with filename");
      }
      const form = new FormData();
      form.append("file", new Blob([data]), filename);
      if (source) form.append("source", source);
      return c.request("POST", `/api/projects/${project_id}/packages/import`, { form });
    },
  }),
  defineTool({
    name: "scan_project",
    title: "Scan now",
    description:
      "Check a project's packages against OSV right away (it also runs on a schedule). Results show up in list_vulnerabilities shortly after.",
    write: true,
    idempotent: true,
    input: { project_id: id("Project") },
    run: ({ project_id }, c) => c.post(`/api/projects/${project_id}/scan`),
  }),
];
