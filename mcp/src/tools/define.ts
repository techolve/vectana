/** Shared helpers for defining tools. Each feature lives in its own file and
 * exports a list of tools; `tools/index.ts` collects them. */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

import type { components } from "../api-types.ts";
import { VectanaError, type VectanaClient } from "../client.ts";

export type Schemas = components["schemas"];

export interface ToolDef<S extends z.ZodRawShape = z.ZodRawShape> {
  name: string;
  title: string;
  description: string;
  input: S;
  /** Changes data. Hidden when the server runs read-only. */
  write?: boolean;
  /** Repeating the call with the same arguments has no further effect. */
  idempotent?: boolean;
  run: (args: z.infer<z.ZodObject<S>>, client: VectanaClient) => Promise<unknown>;
}

export function defineTool<S extends z.ZodRawShape>(def: ToolDef<S>): ToolDef<S> {
  return def;
}

/** A z.enum whose values must list every member of the API's enum `T`, so
 * `npm run typecheck` fails when the API grows a value. */
export function apiEnum<T extends string>() {
  return <const V extends readonly [T, ...T[]]>(
    values: V & ([T] extends [V[number]] ? unknown : { missing: Exclude<T, V[number]> }),
  ) => z.enum(values);
}

export const id = (what: string) => z.string().uuid().describe(`${what} ID (UUID)`);
export const date = (what: string) => z.string().date().describe(`${what} (YYYY-MM-DD)`);

/** Drop keys the caller did not give, so PATCH bodies only touch those
 * fields. `null` stays: it clears a field. */
export function given<T extends object>(args: T): Partial<T> {
  return Object.fromEntries(Object.entries(args).filter(([, v]) => v !== undefined)) as Partial<T>;
}

export function ok(data: unknown): CallToolResult {
  const text = data === null || data === undefined ? "OK" : JSON.stringify(data, null, 2);
  return { content: [{ type: "text", text }] };
}

export function failure(err: unknown): CallToolResult {
  const text =
    err instanceof VectanaError
      ? `Vectana API error ${err.status}: ${err.detail}`
      : `Error: ${err instanceof Error ? err.message : String(err)}`;
  return { content: [{ type: "text", text }], isError: true };
}

export function registerTools(
  server: McpServer,
  client: VectanaClient,
  tools: readonly ToolDef<any>[], // eslint-disable-line @typescript-eslint/no-explicit-any
  opts: { readOnly?: boolean } = {},
): string[] {
  const names: string[] = [];
  for (const t of tools) {
    if (opts.readOnly && t.write) continue;
    server.registerTool(
      t.name,
      {
        title: t.title,
        description: t.description,
        inputSchema: t.input,
        annotations: {
          title: t.title,
          readOnlyHint: !t.write,
          destructiveHint: false,
          idempotentHint: t.idempotent ?? !t.write,
          openWorldHint: false,
        },
      },
      async (args: unknown) => {
        try {
          return ok(await t.run(args as never, client));
        } catch (err) {
          return failure(err);
        }
      },
    );
    names.push(t.name);
  }
  return names;
}
