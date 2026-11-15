/** Vectana MCP over Streamable HTTP (stateless, JSON responses).
 *
 * Meant to run behind the Vectana API, which serves it at /mcp: the API
 * checks the caller's token (and runs the OAuth sign-in for clients such as
 * claude.ai), then forwards the request here. Each request carries its own
 * `Authorization: Bearer vcu_...`, which this server passes on to the API, so
 * every call runs as that user. `X-Vectana-Read-Only: 1` hides write tools.
 */

import { createServer as createHttp, type IncomingMessage, type Server } from "node:http";

import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

import { createServer } from "./server.ts";

export interface HttpOptions {
  /** Vectana API base URL the tools call, e.g. http://127.0.0.1:8000 */
  apiUrl: string;
  fetch?: typeof fetch;
}

const MAX_BODY = 4 * 1024 * 1024;

function bearer(req: IncomingMessage): string | undefined {
  const [scheme, value] = (req.headers.authorization ?? "").split(" ", 2);
  return scheme?.toLowerCase() === "bearer" && value ? value.trim() : undefined;
}

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY) throw new Error("Request body too large");
    chunks.push(chunk as Buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function rpcError(status: number, message: string): [number, string] {
  return [status, JSON.stringify({ jsonrpc: "2.0", error: { code: -32000, message }, id: null })];
}

export function createHttpServer(opts: HttpOptions): Server {
  return createHttp(async (req, res) => {
    const send = ([status, body]: [number, string]) => {
      res.writeHead(status, { "Content-Type": "application/json" }).end(body);
    };
    const path = new URL(req.url ?? "/", "http://localhost").pathname;
    if (path === "/health") return send([200, '{"status":"ok"}']);
    if (path !== "/mcp") return send(rpcError(404, "Not found"));
    if (req.method !== "POST") return send(rpcError(405, "Method not allowed"));
    const token = bearer(req);
    if (!token) return send(rpcError(401, "Missing bearer token"));
    let body: unknown;
    try {
      body = await readJson(req);
    } catch (err) {
      return send(rpcError(400, err instanceof Error ? err.message : "Bad request"));
    }
    const lang = req.headers["accept-language"]?.split(",")[0]?.slice(0, 2);
    const { server } = createServer(
      {
        url: opts.apiUrl,
        token,
        locale: lang === "en" || lang === "ja" ? lang : undefined,
        readOnly: req.headers["x-vectana-read-only"] === "1",
      },
      opts.fetch,
    );
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });
    res.on("close", () => {
      void transport.close();
      void server.close();
    });
    try {
      await server.connect(transport);
      await transport.handleRequest(req, res, body);
    } catch (err) {
      console.error(err);
      if (!res.headersSent) send(rpcError(500, "Internal error"));
    }
  });
}
