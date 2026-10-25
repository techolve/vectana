// Fills a fresh Vectana instance with fictional demo data through the API.
//   node seed.mjs <base-url> <ja|en>
// Expects the group admin (ADMIN_EMAIL / ADMIN_PASSWORD) to exist already.
// Webhooks are added by `seed.mjs ... --webhooks` after the first scan, so the
// scan never posts to them.

import { ADMIN_EMAIL, ADMIN_PASSWORD, USER_PASSWORD, data } from "./data.mjs";

const [base, locale = "ja", ...flags] = process.argv.slice(2);
if (!base) throw new Error("usage: node seed.mjs <base-url> <ja|en> [--webhooks]");
const d = data[locale];

async function call(method, path, body, token) {
  const res = await fetch(`${base}/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "Accept-Language": locale,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${path}: ${res.status} ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

async function login(email, password) {
  return (await call("POST", "/auth/login", { email, password })).access_token;
}

const admin = await login(ADMIN_EMAIL, ADMIN_PASSWORD);
const byName = (rows) => Object.fromEntries(rows.map((r) => [r.name, r]));

if (flags.includes("--webhooks")) {
  const projects = byName(await call("GET", "/projects", undefined, admin));
  for (const [project, hooks] of Object.entries(d.webhooks)) {
    for (const hook of hooks) {
      await call("POST", `/projects/${projects[project].id}/webhooks`, { ...hook, locale }, admin);
    }
  }
  console.log("webhooks added");
  process.exit(0);
}

await call("PUT", "/auth/locale", { locale }, admin);

// Companies (the parent company was created with the admin).
for (const c of d.companies.slice(1)) await call("POST", "/companies", c, admin);
const companies = byName(await call("GET", "/companies", undefined, admin));

// Departments, parents first.
const depts = {};
for (const [company, name, parent] of d.departments) {
  const row = await call(
    "POST",
    "/departments",
    { company_id: companies[company].id, name, parent_id: parent ? depts[parent].id : null },
    admin,
  );
  depts[name] = row;
}

// Users join through invitations, like real ones do.
const users = {};
for (const u of d.users) {
  const inv = await call(
    "POST",
    "/invitations",
    {
      email: u.email,
      display_name: u.name,
      company_id: companies[u.company].id,
      role: u.role,
      locale,
      departments: (u.departments ?? []).map(([name, extra], i) => ({
        department_id: depts[name].id,
        is_primary: i === 0,
        is_head: extra === "head",
      })),
    },
    admin,
  );
  if (u.pending) continue;
  const token = new URL(inv.accept_url).searchParams.get("token");
  await call("POST", "/auth/invitations/accept", { token, password: USER_PASSWORD });
  users[u.email] = await call("GET", "/auth/me", undefined, await login(u.email, USER_PASSWORD));
}

// Projects with packages, runtimes and members.
for (const p of d.projects) {
  const project = await call(
    "POST",
    "/projects",
    {
      name: p.name,
      description: p.description,
      company_id: companies[p.company].id,
      department_id: p.department ? depts[p.department].id : null,
    },
    admin,
  );
  for (const [ecosystem, name, version] of p.packages) {
    await call("POST", `/projects/${project.id}/packages`, { ecosystem, name, version }, admin);
  }
  for (const [product, version] of p.runtimes ?? []) {
    await call("POST", `/projects/${project.id}/runtimes`, { product, version }, admin);
  }
  for (const [email, role] of p.members ?? []) {
    await call("POST", `/projects/${project.id}/members`, { user_id: users[email].id, role }, admin);
  }
}

console.log(`seeded ${locale}: ${d.users.length} users, ${d.projects.length} projects`);
