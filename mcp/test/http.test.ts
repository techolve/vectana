import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { test } from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

import { createHttpServer } from "../src/http.ts";

async function start() {
  const seen: { url: string; auth: string }[] = [];
  const fakeFetch = (async (input: string | URL, init?: RequestInit) => {
    const headers = init?.headers as Record<string, string>;
    seen.push({ url: String(input), auth: headers.Authorization ?? "" });
    return Response.json({ email: "heki@example.com" });
  }) as typeof fetch;
  const server = createHttpServer({ apiUrl: "http://api.test", fetch: fakeFetch });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return { server, seen, url: new URL(`http://127.0.0.1:${port}/mcp`) };
}

async function connect(url: URL, headers: Record<string, string>) {
  const client = new Client({ name: "test", version: "0" });
  await client.connect(new StreamableHTTPClientTransport(url, { requestInit: { headers } }));
  return client;
}

test("serves tools over HTTP with the caller's token", async (t) => {
  const { server, seen, url } = await start();
  t.after(() => server.close());
  const client = await connect(url, { Authorization: "Bearer vcu_abc" });
  const { tools } = await client.listTools();
  assert.ok(tools.some((x) => x.name === "update_vulnerability"));
  const result = await client.callTool({ name: "whoami", arguments: {} });
  assert.ok(!result.isError);
  assert.equal(seen.at(-1)?.url, "http://api.test/api/auth/me");
  assert.equal(seen.at(-1)?.auth, "Bearer vcu_abc");
  await client.close();
});

test("read-only header hides write tools", async (t) => {
  const { server, url } = await start();
  t.after(() => server.close());
  const client = await connect(url, { Authorization: "Bearer vcu_abc", "X-Vectana-Read-Only": "1" });
  const { tools } = await client.listTools();
  assert.ok(tools.length > 0);
  assert.ok(tools.every((x) => x.annotations?.readOnlyHint === true));
  await client.close();
});

test("rejects requests without a token, and GET", async (t) => {
  const { server, url } = await start();
  t.after(() => server.close());
  const post = await fetch(url, { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } });
  assert.equal(post.status, 401);
  assert.equal((await fetch(url)).status, 405);
});
