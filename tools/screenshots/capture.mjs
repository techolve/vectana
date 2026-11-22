// Takes the documentation screenshots from a seeded instance.
//   node capture.mjs <base-url> <ja|en> <out-dir>
// CHROMIUM_PATH points Playwright at an already installed Chromium.

import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { ADMIN_EMAIL, ADMIN_PASSWORD, USER_PASSWORD, data, pm } from "./data.mjs";

const [base, locale, outRoot] = process.argv.slice(2);
if (!outRoot) throw new Error("usage: node capture.mjs <base-url> <ja|en> <out-dir>");
const out = path.join(outRoot, locale);
await mkdir(out, { recursive: true });

const here = path.dirname(fileURLToPath(import.meta.url));
const messages = JSON.parse(await readFile(path.join(here, `../../web/messages/${locale}.json`), "utf8"));
// Tab labels without their "{count}" placeholder, e.g. "パッケージ (".
const label = (text) => text.split("{")[0].trim();

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 2,
  colorScheme: "light",
  locale,
});
let page = await context.newPage();

async function settle() {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
}

async function shot(name, { fullPage = false, target } = {}) {
  await settle();
  const file = path.join(out, `${name}.png`);
  if (target) await target.screenshot({ path: file });
  else await page.screenshot({ path: file, fullPage });
  console.log(`  ${locale}/${name}.png`);
}

async function open(route) {
  await page.goto(`${base}/${locale}${route}`);
  await settle();
}

async function tab(text, name, options) {
  await page.getByRole("tab").filter({ hasText: label(text) }).first().click();
  await shot(name, options);
}

async function login(email, password) {
  await open("/login/");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.getByRole("button", { name: /ログイン|Log in|Sign in/i }).click();
  await page.waitForFunction(() => localStorage.getItem("vectana.access"));
}

async function get(apiPath) {
  return page.evaluate(async (p) => {
    const res = await fetch(`/api${p}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("vectana.access")}` },
    });
    return res.json();
  }, apiPath);
}

// Login: the empty form, then sign in through it.
await open("/login/");
await shot("login");
await login(ADMIN_EMAIL, ADMIN_PASSWORD);

await open("/");
await shot("dashboard");

await open("/org/");
await shot("org-dashboard", { fullPage: true });

await open("/projects/");
await shot("projects");

const projects = await get("/projects");
const idOf = (key) => {
  const name = data[locale].projects.find((p) => p.key === key)?.name ?? pm[locale].deals.find((p) => p.key === key).name;
  return projects.find((p) => p.name === name).id;
};
const tabs = messages.project.tabs;

await open(`/projects/detail/?id=${idOf("portal")}`);
await shot("project-overview");
await tab(tabs.tasks, "project-gantt");
await tab(tabs.security, "project-security");
await tab(tabs.estimates, "project-estimates", { fullPage: true });
await tab(tabs.actuals, "project-actuals", { fullPage: true });
await tab(tabs.vulns, "project-vulns");
await tab(tabs.eol, "project-eol");
await tab(tabs.packages, "project-packages");
await tab(tabs.members, "project-members");
await tab(tabs.repos, "project-repos");
await tab(tabs.webhooks, "project-webhooks");
await tab(tabs.tokens, "project-tokens");

await open(`/projects/detail/?id=${idOf("mobile")}`);
await tab(tabs.tasks, "project-board", { fullPage: true });

await open(`/projects/detail/?id=${idOf("api")}`);
await tab(tabs.tasks, "project-maintenance");

await open(`/projects/detail/?id=${idOf("production")}`);
await shot("deal-overview");
await tab(tabs.activity, "project-activity");

await open("/customers/");
await shot("customers");

await open("/billing/");
await shot("billing");

await open("/vulnerabilities/");
await shot("vulnerabilities");

await open("/eol/");
await shot("eol");

await open("/settings/");
await shot("settings", { fullPage: true });
await shot("personal-tokens", {
  target: page.locator("[data-slot=card]").filter({ hasText: messages.personalTokens.title.split("（")[0].split(" (")[0] }).first(),
});

await open("/admin/");
const admin = messages.admin.tabs;
await shot("admin-companies");
await tab(admin.departments, "admin-departments");
await tab(admin.users, "admin-users");
await tab(admin.invitations, "admin-invitations");
await tab(admin.system, "admin-system");

// The consent page a claude.ai connector opens (remote MCP).
const client = await page.evaluate(async () => {
  const res = await fetch("/api/oauth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_name: "Claude", redirect_uris: ["https://claude.ai/api/mcp/auth_callback"] }),
  });
  return res.json();
});
const query = new URLSearchParams({
  response_type: "code",
  client_id: client.client_id,
  redirect_uri: "https://claude.ai/api/mcp/auth_callback",
  code_challenge: "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
  code_challenge_method: "S256",
  state: "docs",
});
await page.goto(`${base}/oauth/authorize?${query}`);
await shot("oauth-consent");

// Timesheet as a team lead with hours entered.
await context.clearCookies();
await page.evaluate(() => localStorage.clear());
await login(Object.keys(pm[locale].roles)[1], USER_PASSWORD);
await open("/timesheet/");
await shot("timesheet");

await browser.close();
