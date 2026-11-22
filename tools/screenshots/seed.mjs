// Fills a fresh Vectana instance with fictional demo data through the API.
//   node seed.mjs <base-url> <ja|en> [--webhooks | --pm <feeds-url>]
// Expects the group admin (ADMIN_EMAIL / ADMIN_PASSWORD) to exist already.
// Webhooks are added by `seed.mjs ... --webhooks` after the first scan, so the
// scan never posts to them. `--pm` adds the project management data (customers,
// deals, estimates, tasks, sprints, timesheets, billing, tokens and a linked
// repository served by feeds.mjs) on top.

import { ADMIN_EMAIL, ADMIN_PASSWORD, USER_PASSWORD, data, pm } from "./data.mjs";

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

if (flags.includes("--pm")) {
  await seedPm(flags[flags.indexOf("--pm") + 1]);
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
      roles: u.role === "member" ? [] : [u.role],
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

function day(offset) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

function monday(weeksAgo) {
  const d = new Date();
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7 * weeksAgo);
  return d;
}

async function seedPm(feeds) {
  const p = pm[locale];
  const users = Object.fromEntries((await call("GET", "/users", undefined, admin)).map((u) => [u.email, u]));
  const me = await call("GET", "/auth/me", undefined, admin);
  const uid = (email) => (email === ADMIN_EMAIL ? me.id : email ? users[email].id : null);
  for (const [email, body] of Object.entries(p.roles)) await call("PATCH", `/users/${uid(email)}`, body, admin);

  const companies = await call("GET", "/companies", undefined, admin);
  const parent = companies.find((c) => c.type === "parent");
  const customers = {};
  for (const { key, contact, ...c } of p.customers) {
    customers[key] = await call("POST", "/customers", { ...c, company_id: parent.id, sales_owner_id: uid(Object.keys(p.roles)[0]) }, admin);
    await call("POST", `/customers/${customers[key].id}/contacts`, { ...contact, is_primary: true }, admin);
  }

  const projects = {};
  const byProjectName = byName(await call("GET", "/projects", undefined, admin));
  for (const proj of d.projects) projects[proj.key] = byProjectName[proj.name];
  for (const [key, u] of Object.entries(p.projects)) {
    const body = { status: u.status };
    if (u.method) body.method = u.method;
    if (u.customer) body.customer_id = customers[u.customer].id;
    if (u.manager) body.manager_id = uid(u.manager);
    if (u.sales) body.sales_owner_id = uid(u.sales);
    if (u.starts !== undefined) body.starts_on = day(u.starts);
    if (u.ends !== undefined) body.ends_on = day(u.ends);
    projects[key] = await call("PATCH", `/projects/${projects[key].id}`, body, admin);
  }
  for (const deal of p.deals) {
    projects[deal.key] = await call(
      "POST",
      "/projects",
      {
        name: deal.name,
        description: deal.description,
        company_id: parent.id,
        status: deal.status,
        customer_id: customers[deal.customer].id,
        sales_owner_id: uid(Object.keys(p.roles)[0]),
        expected_amount: deal.expected_amount,
        probability: deal.probability,
        next_action: deal.next_action ?? null,
        next_action_on: deal.next_action_on === undefined ? null : day(deal.next_action_on),
      },
      admin,
    );
  }

  // Waterfall tasks with phases, dependencies and a milestone.
  const taskIds = {};
  let previous = null;
  for (const [title, who, start, due, status, progress, children = []] of p.gantt.portal) {
    const phase = await call("POST", `/projects/${projects.portal.id}/tasks`, {
      title, kind: "development", status, progress, assignee_id: uid(who),
      start_date: day(start), due_date: day(due), depends_on: previous ? [previous] : [],
    }, admin);
    taskIds[title] = phase.id;
    previous = phase.id;
    for (const [ctitle, cwho, cstart, cdue, cstatus, cprogress] of children) {
      const child = await call("POST", `/projects/${projects.portal.id}/tasks`, {
        title: ctitle, kind: "development", status: cstatus, progress: cprogress, assignee_id: uid(cwho),
        start_date: day(cstart), due_date: day(cdue), parent_id: phase.id,
      }, admin);
      taskIds[ctitle] = child.id;
    }
  }
  const [mtitle, mday] = p.gantt.milestone;
  await call("POST", `/projects/${projects.portal.id}/tasks`, {
    title: mtitle, kind: "other", is_milestone: true, start_date: day(mday), due_date: day(mday), depends_on: [previous],
  }, admin);

  // Scrum: a closed sprint, an active one and a backlog.
  const scrum = projects[p.scrum.project];
  const addSprintTasks = async (sprint, id) => {
    for (const [title, who, points, status, s] of p.scrum.tasks.filter((t) => t[4] === sprint)) {
      await call("POST", `/projects/${scrum.id}/tasks`, { title, kind: "development", status, points, assignee_id: uid(who), sprint_id: id }, admin);
    }
  };
  for (const [i, s] of p.scrum.sprints.entries()) {
    const sprint = await call("POST", `/projects/${scrum.id}/sprints`, { name: s.name, goal: s.goal, starts_on: day(s.starts), ends_on: day(s.ends), status: "active" }, admin);
    await addSprintTasks(i, sprint.id);
    if (i < p.scrum.sprints.length - 1) await call("PATCH", `/sprints/${sprint.id}`, { status: "closed" }, admin);
  }
  await addSprintTasks(null, null);

  // Maintenance list.
  const maint = projects[p.maintenance.project];
  for (const [title, who, due, status] of p.maintenance.tasks) {
    await call("POST", `/projects/${maint.id}/tasks`, { title, kind: "other", status, assignee_id: uid(who), due_date: day(due) }, admin);
  }

  // Estimates, staged invoices and deal notes.
  for (const [key, estimates] of Object.entries(p.estimates)) {
    for (const e of estimates) {
      const est = await call("POST", `/projects/${projects[key].id}/estimates`, {
        title: e.title, kind: e.kind, amount: e.amount ?? null, status: e.status === "won" ? "submitted" : e.status, billing: "one_time",
        issued_on: day(e.issued_on), valid_until: day(e.issued_on + 30),
        lines: e.lines.map(([label, who, days]) => ({ label, user_id: uid(who), days })),
      }, admin);
      if (e.status === "won") await call("PATCH", `/estimates/${est.id}`, { status: "won", decided_on: day(e.decided_on) }, admin);
      if (e.invoices) {
        const total = (await call("GET", `/estimates/${est.id}`, undefined, admin)).amount;
        const shares = [0.3, 0.4, 0.3];
        const invoices = await call("PUT", `/estimates/${est.id}/invoices`, {
          items: e.invoices.map(([label, planned], i) => ({ label, planned_on: day(planned), amount: Math.round((total * shares[i]) / 1000) * 1000 })),
        }, admin);
        for (const [i, [, planned, status]] of e.invoices.entries()) {
          if (status === "planned") continue;
          const inv = invoices.find((x) => x.planned_on === day(planned)) ?? invoices[i];
          await call("PATCH", `/invoices/${inv.id}`, { status: "invoiced", invoiced_on: day(planned) }, admin);
          if (status === "paid") await call("PATCH", `/invoices/${inv.id}`, { status: "paid", paid_on: day(planned + 25) }, admin);
        }
      }
    }
  }
  for (const [key, notes] of Object.entries(p.activities)) {
    for (const n of notes) {
      await call("POST", `/projects/${projects[key].id}/activities`, {
        kind: n.kind, occurred_on: day(n.occurred_on), participants: n.participants, body: n.body,
        next_action: n.next_action ?? null, next_action_assignee_id: uid(n.next_action_assignee),
        next_action_due: n.next_action_due === undefined ? null : day(n.next_action_due),
      }, admin);
    }
  }

  // Timesheets for the last three weeks, up to today.
  const weeks = p.timesheet[0][3].length;
  for (const email of [...new Set(p.timesheet.map((r) => r[0]))]) {
    for (let w = 0; w < weeks; w++) {
      const start = monday(weeks - 1 - w);
      const rows = p.timesheet
        .filter((r) => r[0] === email)
        .map(([, key, title, hours]) => ({
          project_id: key ? projects[key].id : null,
          task_id: key ? taskIds[title] : null,
          label: key ? null : title,
          hours: [...hours[w], 0, 0].map((h, i) => {
            const date = new Date(start);
            date.setDate(start.getDate() + i);
            return date > new Date() || !h ? null : h;
          }),
        }));
      await call("PUT", "/timesheet", { week_start: start.toISOString().slice(0, 10), user_id: uid(email), rows }, admin);
    }
  }

  // Tokens: personal ones for the admin, a CI token for the portal.
  for (const [name, scope] of p.personalTokens) await call("POST", "/auth/tokens", { name, scope, expires_in_days: 90 }, admin);
  await call("POST", `/projects/${projects.portal.id}/tokens`, { name: p.ciToken }, admin);

  // A linked GitHub repository, served by feeds.mjs.
  if (feeds) {
    await call("POST", `/projects/${projects[p.repo.project].id}/repo-links`, {
      provider: "github", base_url: `${feeds}/github`, repo: p.repo.repo, token: "ghp_demo", sync_issues: true, security_issues: true, import_paths: [], register_webhook: true,
    }, admin);
  }
  console.log(`seeded project management data (${locale})`);
}
