// Takes the documentation screenshots from a seeded instance.
//   node capture.mjs <base-url> <ja|en> <out-dir>

import { mkdir } from "node:fs/promises";
import path from "node:path";

import { chromium } from "playwright";

import { ADMIN_EMAIL, ADMIN_PASSWORD, data } from "./data.mjs";

const [base, locale, outRoot] = process.argv.slice(2);
if (!outRoot) throw new Error("usage: node capture.mjs <base-url> <ja|en> <out-dir>");
const out = path.join(outRoot, locale);
await mkdir(out, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 2,
  colorScheme: "light",
  locale,
});
const page = await context.newPage();

async function settle() {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
}

async function shot(name, { fullPage = false } = {}) {
  await settle();
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage });
  console.log(`  ${locale}/${name}.png`);
}

async function open(route) {
  await page.goto(`${base}/${locale}${route}`);
  await settle();
}

async function tab(index, name) {
  await page.getByRole("tab").nth(index).click();
  await shot(name);
}

// Login: the empty form, then sign in through it.
await open("/login/");
await shot("login");
await page.fill("#email", ADMIN_EMAIL);
await page.fill("#password", ADMIN_PASSWORD);
await page.getByRole("button", { name: /ログイン|Log in|Sign in/i }).click();
await page.waitForFunction(() => localStorage.getItem("vectana.access"));

await open("/");
await shot("dashboard");

await open("/projects/");
await shot("projects");

const portal = data[locale].projects.find((p) => p.key === "portal").name;
const projects = await page.evaluate(async () => {
  const res = await fetch("/api/projects", {
    headers: { Authorization: `Bearer ${localStorage.getItem("vectana.access")}` },
  });
  return res.json();
});
const portalId = projects.find((p) => p.name === portal).id;

await open(`/projects/detail/?id=${portalId}`);
await shot("project-vulns");
await tab(1, "project-eol");
await tab(2, "project-packages");
await tab(3, "project-members");
await tab(4, "project-webhooks");

await open("/vulnerabilities/");
await shot("vulnerabilities");

await open("/eol/");
await shot("eol");

await open("/settings/");
await shot("settings", { fullPage: true });

await open("/admin/");
await shot("admin-companies");
await tab(1, "admin-departments");
await tab(2, "admin-users");
await tab(3, "admin-invitations");
await tab(4, "admin-system");

await browser.close();
