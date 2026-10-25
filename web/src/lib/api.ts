"use client";

// Same-origin API client. Tokens live in localStorage; a 401 triggers one
// refresh attempt before giving up and sending the user to /login/.

const ACCESS = "vectana.access";
const REFRESH = "vectana.refresh";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS, access);
  localStorage.setItem(REFRESH, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
}

export function hasToken() {
  return typeof window !== "undefined" && !!localStorage.getItem(ACCESS);
}

let refreshing: Promise<boolean> | null = null;

async function refresh(): Promise<boolean> {
  const token = localStorage.getItem(REFRESH);
  if (!token) return false;
  refreshing ??= fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: token }),
  })
    .then(async (r) => {
      if (!r.ok) return false;
      const body = await r.json();
      setTokens(body.access_token, body.refresh_token);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

function detail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => e?.msg ?? String(e)).join(", ");
  }
  return fallback;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown; auth?: boolean } = {},
): Promise<T> {
  const { json, auth = true, ...rest } = init;
  const doFetch = () => {
    const headers = new Headers(rest.headers);
    if (json !== undefined) headers.set("Content-Type", "application/json");
    const token = localStorage.getItem(ACCESS);
    if (auth && token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(`/api${path}`, {
      ...rest,
      headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  };

  let res = await doFetch();
  if (res.status === 401 && auth && (await refresh())) res = await doFetch();
  if (res.status === 401 && auth) {
    clearTokens();
    window.location.href = "/login/";
    throw new ApiError(401, "ログインが必要です");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body, res.statusText));
  return body as T;
}

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
export const SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];
export type SeverityCounts = Record<Severity, number>;

export type Me = {
  id: string;
  email: string;
  display_name: string | null;
  role: "group_admin" | "company_admin" | "member";
  company_id: string | null;
  company_name: string | null;
  is_partner: boolean;
  can_manage_org: boolean;
  managed_department_ids: string[];
  group_name: string;
};

export type CompanyType = "parent" | "affiliate" | "partner";
export type Company = { id: string; name: string; type: CompanyType };
export type Department = { id: string; company_id: string; parent_id: string | null; name: string };
export type UserDepartment = { department_id: string; is_primary: boolean; is_head: boolean };
export type User = {
  id: string;
  email: string;
  display_name: string | null;
  role: Me["role"];
  is_active: boolean;
  company_id: string | null;
  departments: UserDepartment[];
};
export type UserBrief = Pick<User, "id" | "email" | "display_name" | "company_id">;
export type Invitation = {
  id: string;
  email: string;
  display_name: string | null;
  company_id: string;
  role: string;
  status: string;
  created_at: string;
  expires_at: string;
  email_sent?: boolean | null;
  accept_url?: string | null;
};

export type Project = {
  id: string;
  company_id: string;
  department_id: string | null;
  name: string;
  description: string | null;
  created_at: string;
  package_count: number;
  open_counts: SeverityCounts;
  my_level: "read" | "write" | "manage" | null;
};
export type ProjectRole = "owner" | "member" | "viewer";
export type Member = {
  id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  company_id: string | null;
  role: ProjectRole;
};
export type Webhook = {
  id: string;
  type: "discord" | "slack";
  url: string;
  min_severity: Severity;
  enabled: boolean;
};
export type Package = {
  id: string;
  ecosystem: string;
  name: string;
  version: string;
  source: string;
  last_scanned_at: string | null;
  open_vulns: number;
};
export type Match = {
  id: string;
  project_id: string;
  project_name: string;
  package_id: string;
  ecosystem: string;
  package_name: string;
  package_version: string;
  vuln_id: string;
  aliases: string[];
  summary: string | null;
  severity: Severity;
  cvss_score: number | null;
  fixed_version: string | null;
  status: "open" | "ack" | "ignored";
  first_seen_at: string;
};
export type Dashboard = {
  project_count: number;
  package_count: number;
  open_counts: SeverityCounts;
  recent: Match[];
};

export const ECOSYSTEMS = ["npm", "PyPI", "Pub", "Maven", "Go", "crates.io", "RubyGems", "Packagist", "NuGet"];

export const ROLE_LABEL: Record<Me["role"], string> = {
  group_admin: "グループ管理者",
  company_admin: "会社管理者",
  member: "メンバー",
};
export const COMPANY_TYPE_LABEL: Record<CompanyType, string> = {
  parent: "親会社",
  affiliate: "関連会社",
  partner: "BP（協力会社）",
};
export const PROJECT_ROLE_LABEL: Record<ProjectRole, string> = {
  owner: "オーナー",
  member: "メンバー",
  viewer: "閲覧のみ",
};
export const STATUS_LABEL: Record<Match["status"], string> = {
  open: "未対応",
  ack: "確認済み",
  ignored: "無視",
};
