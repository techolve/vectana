import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import { configFromEnv, createServer, type Config } from "../src/server.ts";

interface Call {
  method: string;
  url: URL;
  headers: Record<string, string>;
  body: unknown;
}

const PROJECT = "11111111-1111-4111-8111-111111111111";
const MATCH = "22222222-2222-4222-8222-222222222222";

async function connect(config: Partial<Config> = {}, reply: (c: Call) => Response = () => Response.json({ ok: true })) {
  const calls: Call[] = [];
  const fakeFetch = (async (input: string | URL, init?: RequestInit) => {
    const call: Call = {
      method: init?.method ?? "GET",
      url: new URL(String(input)),
      headers: init?.headers as Record<string, string>,
      body: init?.body instanceof FormData ? init.body : init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    return reply(call);
  }) as typeof fetch;
  const { server } = createServer(
    { url: "https://vectana.test/", token: "vcu_secret", locale: "ja", ...config },
    fakeFetch,
  );
  const client = new Client({ name: "test", version: "0" });
  const [a, b] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(a), client.connect(b)]);
  return { client, calls };
}

function text(result: Awaited<ReturnType<Client["callTool"]>>): string {
  const first = (result.content as { type: string; text: string }[])[0];
  return first?.text ?? "";
}

test("lists read and write tools, with annotations", async () => {
  const { client } = await connect();
  const { tools } = await client.listTools();
  const names = tools.map((t) => t.name);
  for (const n of ["whoami", "list_vulnerabilities", "update_vulnerability", "import_dependencies", "create_estimate"]) {
    assert.ok(names.includes(n), n);
  }
  assert.equal(new Set(names).size, names.length, "tool names are unique");
  const update = tools.find((t) => t.name === "update_vulnerability")!;
  assert.equal(update.annotations?.readOnlyHint, false);
  assert.equal(tools.find((t) => t.name === "get_dashboard")!.annotations?.readOnlyHint, true);
});

test("read-only mode hides write tools", async () => {
  const { client } = await connect({ readOnly: true });
  const { tools } = await client.listTools();
  assert.ok(tools.length > 0);
  assert.ok(tools.every((t) => t.annotations?.readOnlyHint === true));
  assert.ok(!tools.some((t) => t.name === "update_vulnerability"));
});

test("sends the token, locale and query", async () => {
  const { client, calls } = await connect();
  await client.callTool({
    name: "list_vulnerabilities",
    arguments: { project_id: PROJECT, status: ["open", "ack"], assignee: "me" },
  });
  const [call] = calls;
  assert.equal(call!.method, "GET");
  assert.equal(call!.url.pathname, "/api/vulnerabilities");
  assert.equal(call!.url.searchParams.get("status"), "open,ack");
  assert.equal(call!.url.searchParams.get("assignee"), "me");
  assert.equal(call!.url.searchParams.get("limit"), "100");
  assert.equal(call!.url.searchParams.get("project_id"), PROJECT);
  assert.equal(call!.headers.Authorization, "Bearer vcu_secret");
  assert.equal(call!.headers["Accept-Language"], "ja");
});

test("PATCH sends only the given fields, keeping null", async () => {
  const { client, calls } = await connect();
  await client.callTool({
    name: "update_vulnerability",
    arguments: { match_id: MATCH, status: "ack", due_date: null },
  });
  assert.equal(calls[0]!.method, "PATCH");
  assert.equal(calls[0]!.url.pathname, `/api/vulnerabilities/${MATCH}`);
  assert.deepEqual(calls[0]!.body, { status: "ack", due_date: null });
});

test("rejects bad arguments before calling the API", async () => {
  const { client, calls } = await connect();
  const result = await client.callTool({
    name: "update_vulnerability",
    arguments: { match_id: MATCH, status: "fixed" },
  });
  assert.equal(result.isError, true);
  assert.equal(calls.length, 0);
});

test("API errors come back as tool errors", async () => {
  const { client } = await connect({}, () =>
    Response.json({ detail: "このトークンは読み取り専用です" }, { status: 403 }),
  );
  const result = await client.callTool({ name: "scan_project", arguments: { project_id: PROJECT } });
  assert.equal(result.isError, true);
  assert.match(text(result), /403: このトークンは読み取り専用です/);
});

test("imports a local file as multipart", async () => {
  const dir = await mkdtemp(join(tmpdir(), "vectana-mcp-"));
  const path = join(dir, "package-lock.json");
  await writeFile(path, '{"lockfileVersion":3,"packages":{}}');
  const { client, calls } = await connect();
  const result = await client.callTool({
    name: "import_dependencies",
    arguments: { project_id: PROJECT, path, source: "web/package-lock.json" },
  });
  assert.equal(result.isError, undefined, text(result));
  const form = calls[0]!.body as FormData;
  assert.equal(calls[0]!.url.pathname, `/api/projects/${PROJECT}/packages/import`);
  const file = form.get("file") as File;
  assert.equal(file.name, "package-lock.json");
  assert.equal(await file.text(), '{"lockfileVersion":3,"packages":{}}');
  assert.equal(form.get("source"), "web/package-lock.json");
});

test("import needs a path or content with a filename", async () => {
  const { client, calls } = await connect();
  const result = await client.callTool({
    name: "import_dependencies",
    arguments: { project_id: PROJECT, content: "lodash==1" },
  });
  assert.equal(result.isError, true);
  assert.equal(calls.length, 0);
});

test("config comes from the environment", () => {
  assert.throws(() => configFromEnv({}), /VECTANA_URL and VECTANA_TOKEN/);
  const config = configFromEnv({
    VECTANA_URL: "https://v.test",
    VECTANA_TOKEN: "vcu_x",
    VECTANA_READ_ONLY: "1",
  });
  assert.deepEqual(config, { url: "https://v.test", token: "vcu_x", locale: undefined, readOnly: true });
});

test("retries once when a kept-alive socket was closed", async () => {
  let n = 0;
  const { client } = await connect({}, () => {
    n += 1;
    if (n === 1) throw new TypeError("fetch failed", { cause: { code: "UND_ERR_SOCKET" } });
    return Response.json({ email: "a@example.com" });
  });
  const result = await client.callTool({ name: "whoami", arguments: {} });
  assert.equal(result.isError, undefined);
  assert.equal(n, 2);
});
