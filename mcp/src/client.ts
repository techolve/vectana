/** A small client for the Vectana REST API. */

export class VectanaError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`Vectana API ${status}: ${detail}`);
  }
}

export type Query = Record<string, string | number | boolean | string[] | undefined>;

export interface RequestOptions {
  query?: Query;
  json?: unknown;
  form?: FormData;
}

export interface ClientOptions {
  baseUrl: string;
  token: string;
  /** Sent as Accept-Language, so error messages come back in this language. */
  locale?: string;
  fetch?: typeof fetch;
}

export class VectanaClient {
  readonly baseUrl: string;
  private readonly token: string;
  private readonly locale?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: ClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.token = opts.token;
    this.locale = opts.locale;
    this.fetchImpl = opts.fetch ?? fetch;
  }

  url(path: string, query?: Query): string {
    const url = new URL(this.baseUrl + path);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value === undefined) continue;
      for (const v of Array.isArray(value) ? value : [value]) {
        url.searchParams.append(key, String(v));
      }
    }
    return url.toString();
  }

  async request<T = unknown>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
      Accept: "application/json",
    };
    if (this.locale) headers["Accept-Language"] = this.locale;
    let body: string | FormData | undefined;
    if (opts.form) {
      body = opts.form;
    } else if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.json);
    }
    const url = this.url(path, opts.query);
    let res: Response;
    try {
      res = await this.fetchImpl(url, { method, headers, body });
    } catch (err) {
      // A kept-alive socket the server already closed: try once more.
      if (!isStaleSocket(err)) throw err;
      res = await this.fetchImpl(url, { method, headers, body });
    }
    const text = await res.text();
    const data: unknown = text ? safeJson(text) : null;
    if (!res.ok) {
      throw new VectanaError(res.status, errorDetail(data, text, res.statusText));
    }
    return data as T;
  }

  get<T = unknown>(path: string, query?: Query): Promise<T> {
    return this.request<T>("GET", path, { query });
  }

  post<T = unknown>(path: string, json?: unknown): Promise<T> {
    return this.request<T>("POST", path, { json: json ?? {} });
  }

  patch<T = unknown>(path: string, json: unknown): Promise<T> {
    return this.request<T>("PATCH", path, { json });
  }

  put<T = unknown>(path: string, json: unknown): Promise<T> {
    return this.request<T>("PUT", path, { json });
  }
}

const STALE_SOCKET = new Set(["UND_ERR_SOCKET", "ECONNRESET", "EPIPE"]);

function isStaleSocket(err: unknown): boolean {
  const code = (err as { cause?: { code?: string } } | null)?.cause?.code;
  return code !== undefined && STALE_SOCKET.has(code);
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorDetail(data: unknown, text: string, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return text || fallback;
}
