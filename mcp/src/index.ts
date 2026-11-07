#!/usr/bin/env node
/** Vectana MCP server over stdio. Configured by environment variables:
 *   VECTANA_URL        e.g. https://vectana.example.com
 *   VECTANA_TOKEN      a personal token (vcu_...)
 *   VECTANA_LOCALE     optional, ja or en (language of error messages)
 *   VECTANA_READ_ONLY  optional, 1 to offer only read tools
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { configFromEnv, createServer, VERSION } from "./server.ts";

async function main(): Promise<void> {
  if (process.argv.includes("--version")) {
    console.log(VERSION);
    return;
  }
  const { server, tools } = createServer(configFromEnv());
  await server.connect(new StdioServerTransport());
  // stdout carries the protocol; logs go to stderr.
  console.error(`vectana-mcp ${VERSION}: ${tools.length} tools`);
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
