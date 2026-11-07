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

export function currentLocale(): string {
  const first = typeof window === "undefined" ? "" : window.location.pathname.split("/")[1];
  return first === "en" ? "en" : "ja";
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

async function request(path: string, init: RequestInit & { json?: unknown; auth?: boolean } = {}): Promise<Response> {
  const { json, auth = true, ...rest } = init;
  const doFetch = () => {
    const headers = new Headers(rest.headers);
    if (json !== undefined) headers.set("Content-Type", "application/json");
    // The API translates its error messages into this language.
    headers.set("Accept-Language", currentLocale());
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
    // Outside React (no router here); a full reload also drops in-memory state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/${currentLocale()}/login/`;
    throw new ApiError(401, "Unauthorized");
  }
  return res;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown; auth?: boolean } = {},
): Promise<T> {
  const res = await request(path, init);
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body, res.statusText));
  return body as T;
}

/** Fetch an authenticated file (e.g. a CSV export) and hand it to the browser as a download. */
export async function apiDownload(path: string, fallbackName: string): Promise<void> {
  const res = await request(path);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, detail(body, res.statusText));
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
export const SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];
export type SeverityCounts = Record<Severity, number>;

/** Global roles; a user holds any number of them (none = plain member). */
export type Role = "group_admin" | "company_admin" | "sales" | "accounting" | "pmo";
export const ROLES: Role[] = ["group_admin", "company_admin", "sales", "accounting", "pmo"];

export type Me = {
  id: string;
  email: string;
  display_name: string | null;
  roles: Role[];
  company_id: string | null;
  company_name: string | null;
  is_partner: boolean;
  can_manage_org: boolean;
  can_sell: boolean; // create customers and estimates
  can_see_customers: boolean;
  managed_department_ids: string[];
  group_name: string;
  locale: string;
};

export type CompanyType = "parent" | "affiliate" | "partner";
export type Company = { id: string; name: string; type: CompanyType };
export type Department = { id: string; company_id: string; parent_id: string | null; name: string };
export type UserDepartment = { department_id: string; is_primary: boolean; is_head: boolean };
export type User = {
  id: string;
  email: string;
  display_name: string | null;
  roles: Role[];
  is_active: boolean;
  company_id: string | null;
  departments: UserDepartment[];
  unit_cost: number | null; // yen per person-day; only for admins, sales and accounting
};
export type UserBrief = Pick<User, "id" | "email" | "display_name" | "company_id">;
export type Invitation = {
  id: string;
  email: string;
  display_name: string | null;
  company_id: string;
  roles: Role[];
  locale: string;
  status: string;
  created_at: string;
  expires_at: string;
  email_sent?: boolean | null;
  accept_url?: string | null;
};

export type ProjectStatus =
  | "inquiry"
  | "proposal"
  | "negotiation"
  | "won"
  | "development"
  | "maintenance"
  | "on_hold"
  | "lost";
export const PROJECT_STATUSES: ProjectStatus[] = [
  "inquiry",
  "proposal",
  "negotiation",
  "won",
  "development",
  "maintenance",
  "on_hold",
  "lost",
];
export const SALES_STATUSES: ProjectStatus[] = ["inquiry", "proposal", "negotiation"];
export const DELIVERY_STATUSES: ProjectStatus[] = ["won", "development", "maintenance"];
export type ProjectMethod = "waterfall" | "scrum";
/** Tabs of the project list. */
export type ProjectTab = "sales" | "active" | "maintenance" | "closed";
export function projectTab(p: Pick<Project, "status" | "archived" | "is_deal">): ProjectTab {
  if (p.archived) return "closed";
  if (p.status === "maintenance") return "maintenance";
  if (p.status ? SALES_STATUSES.includes(p.status) : p.is_deal) return "sales";
  return "active";
}

export type Project = {
  id: string;
  company_id: string;
  department_id: string | null;
  name: string;
  description: string | null;
  created_at: string;
  method: ProjectMethod;
  archived: boolean;
  is_deal: boolean;
  manager: UserBrief | null;
  starts_on: string | null;
  ends_on: string | null;
  // Sales fields: null for partner (BP) users.
  status: ProjectStatus | null;
  customer: { id: string; name: string } | null;
  sales_owner: UserBrief | null;
  ordered_on: string | null;
  expected_amount: number | null;
  probability: number | null;
  next_action: string | null;
  next_action_on: string | null;
  lost_reason: string | null;
  competitor: string | null;
  estimate_count: number | null;
  open_estimate_amount: number | null;
  won_amount: number | null;
  monthly_amount: number | null;
  can_sell: boolean;
  package_count: number;
  open_counts: SeverityCounts;
  eol_counts: EolCounts;
  last_scanned_at: string | null;
  my_level: "read" | "write" | "manage" | null;
};
export type ProjectRole = "owner" | "member" | "viewer";

export type Contact = {
  id: string;
  name: string;
  title: string | null;
  email: string | null;
  phone: string | null;
  is_primary: boolean;
};
export type Customer = {
  id: string;
  company_id: string;
  name: string;
  industry: string | null;
  address: string | null;
  phone: string | null;
  website: string | null;
  payment_terms: string | null;
  billing_contact: string | null;
  notes: string | null;
  sales_owner: UserBrief | null;
  created_at: string;
  primary_contact: string | null;
  project_count: number;
  pipeline_amount: number;
  can_edit: boolean;
};
export type CustomerDetail = Customer & { contacts: Contact[] };

export type EstimateKind = "initial" | "additional" | "maintenance" | "other";
export const ESTIMATE_KINDS: EstimateKind[] = ["initial", "additional", "maintenance", "other"];
export type EstimateStatus = "draft" | "submitted" | "won" | "lost";
export const ESTIMATE_STATUSES: EstimateStatus[] = ["draft", "submitted", "won", "lost"];
export type EstimateLine = {
  id: string;
  label: string;
  user: UserBrief | null;
  days: number;
  unit_cost: number | null; // hidden unless the caller may see per-person costs
  cost: number | null;
};
export type Estimate = {
  id: string;
  project_id: string;
  title: string;
  kind: EstimateKind;
  status: EstimateStatus;
  billing: "one_time" | "monthly";
  amount: number | null;
  effort_days: number | null;
  margin: number | null;
  cost: number | null;
  issued_on: string | null;
  due_on: string | null;
  valid_until: string | null;
  decided_on: string | null;
  lost_reason: string | null;
  competitor: string | null;
  notes: string | null;
  lines: EstimateLine[];
  created_at: string;
  updated_at: string | null;
};

export function hasRole(me: Pick<Me, "roles">, role: Role): boolean {
  return me.roles.includes(role);
}

/** What a pipeline card or a deal row shows as its amount. */
export function dealAmount(p: Pick<Project, "open_estimate_amount" | "won_amount" | "expected_amount">): number | null {
  if (p.open_estimate_amount) return p.open_estimate_amount;
  if (p.won_amount) return p.won_amount;
  return p.expected_amount;
}

/** ¥1,234,000 */
export function yen(amount: number | null | undefined): string {
  return amount == null ? "—" : `¥${amount.toLocaleString("ja-JP")}`;
}
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
  locale: string;
  enabled: boolean;
};
export type ApiToken = {
  id: string;
  name: string;
  prefix: string;
  created_by_email: string | null;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
};
export type UpgradeBump = "patch" | "minor" | "major" | "unknown";
/** Lowest version that fixes every unresolved (not ignored) vulnerability of a package. */
export type Upgrade = {
  version: string | null; // null when none of them has a published fix
  bump: UpgradeBump | null;
  unfixed: number; // unresolved vulnerabilities with no published fix
};
export type Package = {
  id: string;
  ecosystem: string;
  name: string;
  version: string;
  source: string;
  last_scanned_at: string | null;
  open_vulns: number;
  upgrade: Upgrade | null;
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
  status: MatchStatus;
  first_seen_at: string;
  upgrade: Upgrade | null;
  assignee: UserBrief | null;
  due_date: string | null; // YYYY-MM-DD
  sla_due_date: string | null; // SLA deadline when due_date is unset
  updated_at: string | null;
  comment_count: number;
};
export type MatchStatus = "open" | "ack" | "ignored";
export const MATCH_STATUSES: MatchStatus[] = ["open", "ack", "ignored"];
export type MatchEvent = {
  id: string;
  kind: "comment" | "status" | "assignee" | "due_date";
  user: UserBrief | null;
  old_value: string | null;
  new_value: string | null;
  old_user: UserBrief | null;
  new_user: UserBrief | null;
  body: string | null;
  created_at: string;
};
export type MatchDetail = Match & { events: MatchEvent[] };
export type TriageCounts = { mine: number; overdue: number; unassigned: number };

/** Today as YYYY-MM-DD in the browser's timezone. */
export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Unresolved and past its due date. */
/** The match's own due date, or the SLA deadline when none is set. */
export function effectiveDue(m: Pick<Match, "due_date" | "sla_due_date">): string | null {
  return m.due_date ?? m.sla_due_date ?? null;
}
export function isOverdue(m: Pick<Match, "status" | "due_date" | "sla_due_date">): boolean {
  const due = effectiveDue(m);
  return m.status !== "ignored" && !!due && due < todayISO();
}
export type EolCounts = { eol: number; approaching: number };
export type EolStatus = "eol" | "approaching" | "supported" | "unknown";
export const EOL_STATUSES: EolStatus[] = ["eol", "approaching", "supported", "unknown"];
export type EolFinding = {
  id: string;
  project_id: string;
  project_name: string;
  source: "package" | "runtime";
  product: string;
  product_label: string;
  version: string;
  cycle: string | null;
  eol_date: string | null;
  latest: string | null;
  status: EolStatus;
  checked_at: string | null;
};
export type Runtime = { id: string; product: string; version: string; source: string };
export type EolProduct = { name: string; label: string; category: string | null };
export type SystemSettings = {
  eol_warning_days: number;
  sla_critical_days: number;
  sla_high_days: number;
  sla_medium_days: number;
  sla_low_days: number;
  sla_unknown_days: number;
  report_enabled: boolean;
  report_weekday: number; // 0 = Monday
};

export type OrgRow = {
  kind: "total" | "company" | "department" | "unassigned";
  id: string | null;
  company_id: string | null;
  parent_id: string | null;
  name: string;
  depth: number;
  complete: boolean;
  project_count: number;
  open_counts: SeverityCounts;
  overdue: number;
  oldest_overdue_days: number | null;
  eol_counts: EolCounts;
  nearest_eol_date: string | null;
  nearest_eol_days: number | null;
};
export type OverdueItem = {
  match_id: string;
  company_id: string;
  project_id: string;
  project_name: string;
  package_name: string;
  package_version: string;
  vuln_id: string;
  severity: Severity;
  status: "open" | "ack";
  first_seen_at: string;
  due_date: string;
  days_overdue: number;
};
export type UpcomingEol = {
  finding_id: string;
  company_id: string;
  project_id: string;
  project_name: string;
  product: string;
  product_label: string;
  version: string;
  cycle: string | null;
  eol_date: string;
  days_left: number;
};
export type OrgDashboard = {
  today: string;
  sla_days: Record<Severity, number>;
  totals: OrgRow;
  rows: OrgRow[];
  overdue: OverdueItem[];
  upcoming_eol: UpcomingEol[];
};

export type Dashboard = {
  project_count: number;
  package_count: number;
  open_counts: SeverityCounts;
  eol_counts: EolCounts;
  triage: TriageCounts;
  projects: Project[];
  recent: Match[];
  eol: EolFinding[];
};

export const ECOSYSTEMS = ["npm", "PyPI", "Pub", "Maven", "Go", "crates.io", "RubyGems", "Packagist", "NuGet"];

export type Health = { status: string; version: string };
