import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import { VectanaClient } from "./client.ts";
import { registerTools } from "./tools/define.ts";
import { allTools } from "./tools/index.ts";

export const VERSION = "1.1.0";

const INSTRUCTIONS = `Vectana tracks the dependencies of software projects, their vulnerabilities (from OSV) and end-of-life dates (from endoflife.date), and manages projects, deals, customers and estimates.
Every call runs with the permissions of the user who issued the token: call whoami to see who that is.
IDs are UUIDs: find them with the list_* tools first. Update tools only change the fields you pass.`;

export interface Config {
  url: string;
  token: string;
  locale?: string;
  readOnly?: boolean;
}

export function configFromEnv(env: NodeJS.ProcessEnv = process.env): Config {
  const url = env.VECTANA_URL?.trim();
  const token = env.VECTANA_TOKEN?.trim();
  const missing = [!url && "VECTANA_URL", !token && "VECTANA_TOKEN"].filter(Boolean);
  if (missing.length) {
    throw new Error(
      `Set ${missing.join(" and ")}. Issue a personal token in Vectana under Account settings → Personal tokens.`,
    );
  }
  return {
    url: url!,
    token: token!,
    locale: env.VECTANA_LOCALE?.trim() || undefined,
    readOnly: ["1", "true", "yes"].includes((env.VECTANA_READ_ONLY ?? "").toLowerCase()),
  };
}

export function createServer(config: Config, fetchImpl?: typeof fetch) {
  const client = new VectanaClient({
    baseUrl: config.url,
    token: config.token,
    locale: config.locale,
    fetch: fetchImpl,
  });
  const server = new McpServer(
    { name: "vectana", version: VERSION },
    { instructions: INSTRUCTIONS },
  );
  const tools = registerTools(server, client, allTools, { readOnly: config.readOnly });
  return { server, client, tools };
}
