#!/usr/bin/env node
/** Vectana MCP server over stdio. Configured by environment variables:
 *   VECTANA_URL        e.g. https://vectana.example.com
 *   VECTANA_TOKEN      a personal token (vcu_...)
 *   VECTANA_LOCALE     optional, ja or en (language of error messages)
 *   VECTANA_READ_ONLY  optional, 1 to offer only read tools
 *
 * With --http it serves Streamable HTTP instead (used by the Vectana API for
 * its /mcp endpoint; see http.ts). Each request brings its own token, so only
 * VECTANA_URL is needed, plus VECTANA_MCP_HOST / VECTANA_MCP_PORT
 * (default 127.0.0.1:8001).
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { createHttpServer } from "./http.ts";
import { configFromEnv, createServer, VERSION } from "./server.ts";

async function serveHttp(): Promise<void> {
  const apiUrl = process.env.VECTANA_URL?.trim();
  if (!apiUrl) throw new Error("Set VECTANA_URL");
  const host = process.env.VECTANA_MCP_HOST?.trim() || "127.0.0.1";
  const port = Number(process.env.VECTANA_MCP_PORT ?? 8001);
  const server = createHttpServer({ apiUrl });
  server.listen(port, host, () => {
    console.error(`vectana-mcp ${VERSION}: HTTP on ${host}:${port}, API ${apiUrl}`);
  });
  for (const sig of ["SIGTERM", "SIGINT"] as const) {
    process.on(sig, () => server.close(() => process.exit(0)));
  }
}

async function main(): Promise<void> {
  if (process.argv.includes("--version")) {
    console.log(VERSION);
    return;
  }
  if (process.argv.includes("--http")) return serveHttp();
  const { server, tools } = createServer(configFromEnv());
  await server.connect(new StdioServerTransport());
  // stdout carries the protocol; logs go to stderr.
  console.error(`vectana-mcp ${VERSION}: ${tools.length} tools`);
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
