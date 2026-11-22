// Offline stand-ins for OSV.dev and endoflife.date, so screenshots can be taken
// without network access and always show the same findings.
//   node feeds.mjs <port>
// Point the API at it with OSV_BASE_URL=http://127.0.0.1:<port>/osv and
// EOL_BASE_URL=http://127.0.0.1:<port>/eol. /github is just enough of the
// GitHub API to link a repository (an empty one with no open issues). The advisories are real ones for
// the package versions in data.mjs; only the fields Vectana reads are kept.

import http from "node:http";

const port = Number(process.argv[2] ?? 8098);

// [id, ecosystem, package, affected version, fixed, severity, summary, aliases]
const advisories = [
  ["GHSA-f82v-jwr5-mffw", "npm", "next", "14.1.0", "14.2.25", "CRITICAL", "Authorization Bypass in Next.js Middleware", ["CVE-2025-29927"]],
  ["GHSA-fr5h-rqp8-mj6g", "npm", "next", "14.1.0", "14.1.1", "HIGH", "Server-Side Request Forgery in Server Actions", ["CVE-2024-34351"]],
  ["GHSA-gp8f-8m3g-qvj9", "npm", "next", "14.1.0", "14.2.10", "HIGH", "Next.js Cache Poisoning", ["CVE-2024-46982"]],
  ["GHSA-fjxv-7rqg-78g4", "npm", "form-data", "4.0.0", "4.0.4", "CRITICAL", "form-data uses unsafe random function for choosing boundary", ["CVE-2025-7783"]],
  ["GHSA-8cf7-32gw-wr33", "npm", "jsonwebtoken", "8.5.1", "9.0.0", "HIGH", "jsonwebtoken unrestricted key type could lead to legacy keys usage", ["CVE-2022-23539"]],
  ["GHSA-hjrf-2m68-5959", "npm", "jsonwebtoken", "8.5.1", "9.0.0", "MEDIUM", "jsonwebtoken's insecure implementation of key retrieval function could lead to Forgeable Public/Private Tokens", ["CVE-2022-23541"]],
  ["GHSA-qwph-4952-7xr6", "npm", "jsonwebtoken", "8.5.1", "9.0.0", "MEDIUM", "jsonwebtoken vulnerable to signature validation bypass due to insecure default algorithm", ["CVE-2022-23540"]],
  ["GHSA-35jh-r3h4-6jhm", "npm", "lodash", "4.17.20", "4.17.21", "HIGH", "Command Injection in lodash", ["CVE-2021-23337"]],
  ["GHSA-29mw-wpgm-hmr9", "npm", "lodash", "4.17.20", "4.17.21", "MEDIUM", "Regular Expression Denial of Service (ReDoS) in lodash", ["CVE-2020-28500"]],
  ["GHSA-pv4p-cwwg-4rph", "PyPI", "django", "4.2.10", "4.2.15", "CRITICAL", "Django SQL injection in QuerySet.values() and values_list()", ["CVE-2024-42005"]],
  ["GHSA-qg2p-9jwr-mmqf", "PyPI", "django", "4.2.10", "4.2.14", "HIGH", "Django denial-of-service in django.utils.html.urlize()", ["CVE-2024-38875"]],
  ["GHSA-vm8q-m57g-pff3", "PyPI", "django", "4.2.10", "4.2.11", "MEDIUM", "Django denial-of-service in Truncator.words()", ["CVE-2024-27351"]],
  ["GHSA-9wx4-h78v-vm56", "PyPI", "requests", "2.31.0", "2.32.0", "MEDIUM", "Requests Session object does not verify requests after making first request with verify=False", ["CVE-2024-35195"]],
  ["GHSA-9hjg-9r4m-mvj7", "PyPI", "requests", "2.31.0", "2.32.4", "MEDIUM", "Requests vulnerable to .netrc credentials leak via malicious URLs", ["CVE-2024-47081"]],
  ["GHSA-4rgh-jx4f-qfcq", "Pub", "http", "0.13.0", "0.13.3", "MEDIUM", "http before 0.13.3 vulnerable to header injection", ["CVE-2020-35669"]],
  ["GHSA-q2x7-8rv6-6q7h", "PyPI", "jinja2", "3.1.4", "3.1.5", "MEDIUM", "Jinja has a sandbox breakout through indirect reference to format method", ["CVE-2024-56201"]],
  ["GHSA-gmj6-6f8f-6699", "PyPI", "jinja2", "3.1.4", "3.1.5", "MEDIUM", "Jinja has a sandbox breakout through malicious filenames", ["CVE-2024-56326"]],
  ["GHSA-cpwx-vrp4-4pq7", "PyPI", "jinja2", "3.1.4", "3.1.6", "MEDIUM", "Jinja2 vulnerable to sandbox breakout through attr filter selecting format method", ["CVE-2025-27516"]],
  ["GHSA-w3h3-4rj7-4ph4", "PyPI", "gunicorn", "21.2.0", "22.0.0", "HIGH", "Request smuggling leading to endpoint restriction bypass in Gunicorn", ["CVE-2024-1135"]],
  ["GHSA-hc5x-x2vx-497g", "PyPI", "gunicorn", "21.2.0", "23.0.0", "HIGH", "Gunicorn HTTP Request/Response Smuggling vulnerability", ["CVE-2024-6827"]],
];

const osvVuln = ([id, ecosystem, name, , fixed, severity, summary, aliases]) => ({
  id,
  summary,
  aliases,
  database_specific: { severity: severity === "MEDIUM" ? "MODERATE" : severity },
  affected: [
    {
      package: { ecosystem, name },
      ranges: [{ type: "ECOSYSTEM", events: [{ introduced: "0" }, { fixed }] }],
    },
  ],
});

// endoflife.date v1: [product, label, purls, [cycle, eolFrom, latest]]
const products = [
  ["nodejs", "Node.js", [], [["24", "2028-04-30", "24.11.1"], ["22", "2027-04-30", "22.21.1"], ["20", "2026-04-30", "20.19.5"], ["18", "2025-04-30", "18.20.8"]]],
  ["python", "Python", [], [["3.14", "2030-10-31", "3.14.0"], ["3.13", "2029-10-31", "3.13.9"], ["3.12", "2028-10-31", "3.12.12"], ["3.11", "2027-10-31", "3.11.14"], ["3.10", "2026-10-31", "3.10.19"], ["3.9", "2025-10-31", "3.9.25"]]],
  ["postgresql", "PostgreSQL", [], [["18", "2030-11-14", "18.1"], ["17", "2029-11-08", "17.7"], ["16", "2028-11-09", "16.11"], ["15", "2027-11-11", "15.15"], ["14", "2026-11-12", "14.20"]]],
  ["ubuntu", "Ubuntu", [], [["24.04", "2029-05-31", "24.04.3"], ["22.04", "2027-06-01", "22.04.5"], ["20.04", "2025-05-29", "20.04.6"]]],
  ["php", "PHP", [], [["8.4", "2028-12-31", "8.4.14"], ["8.3", "2027-12-31", "8.3.27"], ["8.2", "2026-12-31", "8.2.29"]]],
  ["nextjs", "Next.js", ["pkg:npm/next"], [["16", null, "16.4.5"], ["15", "2026-10-21", "15.5.6"], ["14", "2025-10-26", "14.2.33"]]],
  ["django", "Django", ["pkg:pypi/django"], [["5.2", "2028-04-30", "5.2.8"], ["4.2", "2026-04-30", "4.2.26"]]],
  ["react", "React", ["pkg:npm/react"], [["19", null, "19.2.4"], ["18", null, "18.3.1"]]],
];

const today = new Date().toISOString().slice(0, 10);
const eolProduct = ([name, label, , releases]) => ({
  name,
  label,
  releases: releases.map(([cycle, eolFrom, latest]) => ({
    name: cycle,
    eolFrom,
    isEol: eolFrom !== null && eolFrom <= today,
    latest: { name: latest },
  })),
});

let issueNo = 0;

function send(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

async function readJson(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}

http
  .createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");
    const p = decodeURIComponent(url.pathname);
    if (req.method === "POST" && p === "/osv/v1/querybatch") {
      const { queries = [] } = await readJson(req);
      const results = queries.map(({ package: pkg, version }) => ({
        vulns: advisories
          .filter((a) => a[1] === pkg.ecosystem && a[2].toLowerCase() === pkg.name.toLowerCase() && a[3] === version)
          .map((a) => ({ id: a[0] })),
      }));
      return send(res, 200, { results });
    }
    if (p.startsWith("/osv/v1/vulns/")) {
      const a = advisories.find((x) => x[0] === p.slice("/osv/v1/vulns/".length));
      return a ? send(res, 200, osvVuln(a)) : send(res, 404, {});
    }
    if (p === "/eol/products") {
      return send(res, 200, { result: products.map(([name, label]) => ({ name, label, aliases: [] })) });
    }
    if (p.startsWith("/eol/products/")) {
      const prod = products.find((x) => x[0] === p.slice("/eol/products/".length));
      return prod ? send(res, 200, { result: eolProduct(prod) }) : send(res, 404, {});
    }
    if (p === "/eol/identifiers/purl") {
      const rows = products.flatMap(([name, , purls]) => purls.map((identifier) => ({ identifier, product: { name } })));
      return send(res, 200, { result: rows });
    }
    const gh = p.match(/^\/github\/repos\/[^/]+\/[^/]+(\/.*)?$/);
    if (gh) {
      const rest = gh[1] ?? "";
      if (rest === "") return send(res, 200, { default_branch: "main" });
      if (rest === "/hooks") return send(res, 201, { id: 1 });
      if (rest.startsWith("/commits/")) return send(res, 200, { sha: "9f3c2a1e4b7d8c6a5f0e1d2c3b4a59687f6e5d4c" });
      if (rest.startsWith("/git/trees/")) return send(res, 200, { tree: [] });
      if (rest === "/issues" && req.method === "POST") {
        const body = await readJson(req);
        issueNo += 1;
        return send(res, 201, { number: issueNo, state: "open", html_url: `https://github.com/example/${issueNo}`, ...body, labels: [] });
      }
      const issue = rest.match(/^\/issues\/(\d+)$/);
      if (issue) {
        const body = req.method === "GET" ? {} : await readJson(req);
        return send(res, 200, { number: Number(issue[1]), state: "open", html_url: "", ...body, labels: [] });
      }
      if (rest === "/milestones" && req.method === "POST") {
        const body = await readJson(req);
        issueNo += 1;
        return send(res, 201, { number: issueNo, state: "open", ...body });
      }
      if (rest === "/issues" || rest === "/milestones") return send(res, 200, []);
    }
    send(res, 404, {});
  })
  .listen(port, "127.0.0.1", () => console.log(`feeds on http://127.0.0.1:${port}`));
