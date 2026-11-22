// Fictional demo data for documentation screenshots. Same shape per locale so
// the English screenshots show English names. Package versions are picked to
// hit known OSV advisories and endoflife.date cycles.

export const ADMIN_EMAIL = "admin@example.com";
export const ADMIN_PASSWORD = "vectana-demo-admin";
export const USER_PASSWORD = "vectana-demo-user";

const packages = {
  portal: [
    ["npm", "next", "14.1.0"],
    ["npm", "react", "19.2.4"],
    ["npm", "form-data", "4.0.0"],
    ["npm", "jsonwebtoken", "8.5.1"],
    ["npm", "lodash", "4.17.20"],
    ["npm", "dayjs", "1.11.13"],
  ],
  api: [
    ["PyPI", "django", "4.2.10"],
    ["PyPI", "djangorestframework", "3.14.0"],
    ["PyPI", "requests", "2.31.0"],
    ["PyPI", "celery", "5.4.0"],
  ],
  mobile: [
    ["Pub", "http", "0.13.0"],
    ["Pub", "provider", "6.1.2"],
    ["Pub", "shared_preferences", "2.3.2"],
  ],
  booking: [
    ["PyPI", "flask", "2.3.2"],
    ["PyPI", "jinja2", "3.1.4"],
    ["PyPI", "gunicorn", "21.2.0"],
  ],
};

const runtimes = {
  portal: [["nodejs", "18"]],
  api: [
    ["python", "3.11"],
    ["postgresql", "14"],
  ],
  mobile: [],
  booking: [
    ["python", "3.9"],
    ["ubuntu", "20.04"],
  ],
};

export const data = {
  ja: {
    companies: [
      { name: "サンプル株式会社", type: "parent" },
      { name: "サンプルソリューションズ株式会社", type: "affiliate" },
      { name: "パートナーテック合同会社", type: "partner" },
    ],
    // [company, name, parent]
    departments: [
      ["サンプル株式会社", "開発本部"],
      ["サンプル株式会社", "Webチーム", "開発本部"],
      ["サンプル株式会社", "モバイルチーム", "開発本部"],
      ["サンプル株式会社", "情報システム部"],
      ["サンプルソリューションズ株式会社", "システム開発部"],
    ],
    users: [
      { email: "sato@example.com", name: "佐藤 花子", company: "サンプル株式会社", role: "company_admin", departments: [["開発本部", "head"]] },
      { email: "suzuki@example.com", name: "鈴木 一郎", company: "サンプル株式会社", role: "member", departments: [["Webチーム", "head"], ["モバイルチーム"]] },
      { email: "takahashi@example.com", name: "高橋 健", company: "サンプル株式会社", role: "member", departments: [["モバイルチーム"]] },
      { email: "tanaka@example.com", name: "田中 美咲", company: "サンプルソリューションズ株式会社", role: "company_admin", departments: [["システム開発部", "head"]] },
      { email: "ito@example.net", name: "伊藤 翔", company: "パートナーテック合同会社", role: "member" },
      { email: "watanabe@example.com", name: "渡辺 誠", company: "サンプル株式会社", role: "member", departments: [["情報システム部"]], pending: true },
      { email: "kobayashi@example.net", name: "小林 優", company: "パートナーテック合同会社", role: "member", pending: true },
    ],
    projects: [
      {
        key: "portal", name: "顧客ポータル", company: "サンプル株式会社", department: "Webチーム",
        description: "お客様向けの会員サイト（Next.js）",
        members: [["suzuki@example.com", "owner"], ["ito@example.net", "member"]],
      },
      {
        key: "api", name: "社内API", company: "サンプル株式会社", department: "開発本部",
        description: "業務システム共通のバックエンド（Django REST Framework）",
        members: [["suzuki@example.com", "member"], ["sato@example.com", "owner"]],
      },
      {
        key: "mobile", name: "店舗アプリ", company: "サンプル株式会社", department: "モバイルチーム",
        description: "店舗スタッフ向けの Flutter アプリ",
        members: [["takahashi@example.com", "owner"], ["suzuki@example.com", "member"]],
      },
      {
        key: "booking", name: "予約システム", company: "サンプルソリューションズ株式会社", department: "システム開発部",
        description: "会議室・設備の予約システム（Flask）",
        members: [["tanaka@example.com", "owner"]],
      },
    ].map((p) => ({ ...p, packages: packages[p.key], runtimes: runtimes[p.key] })),
    webhooks: {
      顧客ポータル: [
        { type: "discord", url: "https://discord.com/api/webhooks/000000000000000000/example", min_severity: "HIGH" },
        { type: "slack", url: "https://hooks.slack.com/services/T00000000/B00000000/example", min_severity: "MEDIUM" },
      ],
    },
  },
  en: {
    companies: [
      { name: "Example Inc.", type: "parent" },
      { name: "Example Solutions Ltd.", type: "affiliate" },
      { name: "Partner Tech LLC", type: "partner" },
    ],
    departments: [
      ["Example Inc.", "Engineering"],
      ["Example Inc.", "Web Team", "Engineering"],
      ["Example Inc.", "Mobile Team", "Engineering"],
      ["Example Inc.", "IT"],
      ["Example Solutions Ltd.", "Development"],
    ],
    users: [
      { email: "olivia@example.com", name: "Olivia Smith", company: "Example Inc.", role: "company_admin", departments: [["Engineering", "head"]] },
      { email: "james@example.com", name: "James Brown", company: "Example Inc.", role: "member", departments: [["Web Team", "head"], ["Mobile Team"]] },
      { email: "emma@example.com", name: "Emma Wilson", company: "Example Inc.", role: "member", departments: [["Mobile Team"]] },
      { email: "liam@example.com", name: "Liam Taylor", company: "Example Solutions Ltd.", role: "company_admin", departments: [["Development", "head"]] },
      { email: "noah@example.net", name: "Noah Davis", company: "Partner Tech LLC", role: "member" },
      { email: "ava@example.com", name: "Ava Johnson", company: "Example Inc.", role: "member", departments: [["IT"]], pending: true },
      { email: "mia@example.net", name: "Mia Clark", company: "Partner Tech LLC", role: "member", pending: true },
    ],
    projects: [
      {
        key: "portal", name: "Customer Portal", company: "Example Inc.", department: "Web Team",
        description: "Customer-facing member site (Next.js)",
        members: [["james@example.com", "owner"], ["noah@example.net", "member"]],
      },
      {
        key: "api", name: "Internal API", company: "Example Inc.", department: "Engineering",
        description: "Shared backend for business systems (Django REST Framework)",
        members: [["james@example.com", "member"], ["olivia@example.com", "owner"]],
      },
      {
        key: "mobile", name: "Store App", company: "Example Inc.", department: "Mobile Team",
        description: "Flutter app for store staff",
        members: [["emma@example.com", "owner"], ["james@example.com", "member"]],
      },
      {
        key: "booking", name: "Booking System", company: "Example Solutions Ltd.", department: "Development",
        description: "Meeting room and equipment booking (Flask)",
        members: [["liam@example.com", "owner"]],
      },
    ].map((p) => ({ ...p, packages: packages[p.key], runtimes: runtimes[p.key] })),
    webhooks: {
      "Customer Portal": [
        { type: "discord", url: "https://discord.com/api/webhooks/000000000000000000/example", min_severity: "HIGH" },
        { type: "slack", url: "https://hooks.slack.com/services/T00000000/B00000000/example", min_severity: "MEDIUM" },
      ],
    },
  },
};

// Admin display names / parent company, passed to `app.cli create-admin`.
export const admin = {
  ja: { name: "山田 太郎", company: "サンプル株式会社", group: "サンプルグループ" },
  en: { name: "Alex Morgan", company: "Example Inc.", group: "Example Group" },
};

// Project management demo data (customers, deals, estimates, tasks, sprints,
// timesheets, billing), added by `seed.mjs ... --pm` after the first scan.
// Dates are days from today, so the screenshots always look current.
export const pm = {
  ja: {
    roles: {
      "sato@example.com": { roles: ["company_admin", "sales"], unit_cost: 60000 },
      "suzuki@example.com": { unit_cost: 55000 },
      "takahashi@example.com": { unit_cost: 50000 },
      "ito@example.net": { unit_cost: 45000 },
    },
    customers: [
      { key: "minato", name: "みなと物流株式会社", industry: "物流", address: "神奈川県横浜市中区海岸通 1-1", phone: "045-000-0000", payment_terms: "月末締め翌月末払い", contact: { name: "山本 直樹", title: "情報システム課 課長", email: "yamamoto@minato.example" } },
      { key: "sakura", name: "さくら不動産株式会社", industry: "不動産", address: "東京都渋谷区桜丘町 2-2", phone: "03-0000-0000", payment_terms: "月末締め翌月末払い", contact: { name: "中村 恵", title: "経営企画部", email: "nakamura@sakura.example" } },
      { key: "hokuto", name: "北斗製作所株式会社", industry: "製造", address: "愛知県名古屋市中村区 3-3", phone: "052-000-0000", payment_terms: "20日締め翌月20日払い", contact: { name: "加藤 大輔", title: "生産管理部 部長", email: "kato@hokuto.example" } },
    ],
    // Updates to the projects from `data`, by key.
    projects: {
      portal: { status: "development", method: "waterfall", customer: "minato", manager: "suzuki@example.com", sales: "sato@example.com", starts: -42, ends: 60 },
      api: { status: "maintenance" },
      mobile: { status: "development", method: "scrum", customer: "sakura", manager: "takahashi@example.com", sales: "sato@example.com", starts: -35, ends: 90 },
      booking: { status: "development", method: "waterfall" },
    },
    deals: [
      { key: "production", name: "生産管理システム刷新", description: "工場の生産計画・実績管理を Web 化", status: "negotiation", customer: "hokuto", expected_amount: 18000000, probability: 60, next_action: "提案書の最終版を送付", next_action_on: 3 },
      { key: "search", name: "物件検索アプリ", description: "賃貸物件の検索・内見予約アプリ", status: "proposal", customer: "sakura", expected_amount: 6500000, probability: 40, next_action: "概算見積を提出", next_action_on: 7 },
      { key: "delivery", name: "配送アプリ改修", description: "ドライバー向けアプリの機能追加", status: "inquiry", customer: "minato", expected_amount: 3000000, probability: 20 },
    ],
    estimates: {
      portal: [
        { title: "顧客ポータル 初期開発", kind: "initial", amount: 9800000, status: "won", issued_on: -60, decided_on: -45, lines: [["要件定義・設計", "suzuki@example.com", 20], ["開発（フロントエンド）", "ito@example.net", 40], ["開発（バックエンド）", "suzuki@example.com", 35], ["テスト", "ito@example.net", 20]], invoices: [["着手金", -40, "paid"], ["中間金", -5, "invoiced"], ["検収後", 62, "planned"]] },
        { title: "会員ランク機能 追加開発", kind: "additional", amount: 1600000, status: "submitted", issued_on: -4, lines: [["設計", "suzuki@example.com", 5], ["開発・テスト", "ito@example.net", 15]] },
      ],
      production: [
        { title: "生産管理システム刷新 概算", kind: "initial", amount: 18000000, status: "submitted", issued_on: -10, lines: [["要件定義", "sato@example.com", 30], ["設計・開発", "suzuki@example.com", 180], ["テスト・移行", "takahashi@example.com", 60]] },
      ],
    },
    activities: {
      production: [
        { kind: "meeting", occurred_on: -14, participants: "加藤部長、佐藤", body: "現行システムの課題をヒアリング。紙の作業日報をなくしたい、在庫と生産計画を連動させたいとの要望。" },
        { kind: "email", occurred_on: -3, participants: "加藤部長", body: "概算見積を送付。来週中に社内で検討するとのこと。", next_action: "提案書の最終版を送付", next_action_assignee: "sato@example.com", next_action_due: 3 },
      ],
    },
    // Waterfall tasks: [title, assignee, start, due, status, progress, children?]
    gantt: {
      portal: [
        ["要件定義", "suzuki@example.com", -42, -29, "done", 100, [["業務ヒアリング", "suzuki@example.com", -42, -36, "done", 100], ["要件定義書の作成", "suzuki@example.com", -35, -29, "done", 100]]],
        ["基本設計", "suzuki@example.com", -28, -15, "done", 100, [["画面設計", "ito@example.net", -28, -20, "done", 100], ["API 設計", "suzuki@example.com", -24, -15, "done", 100]]],
        ["開発", "suzuki@example.com", -14, 30, "in_progress", 30, [["会員登録・ログイン", "suzuki@example.com", -14, 2, "in_progress", 70], ["マイページ", "ito@example.net", -4, 16, "in_progress", 20], ["お知らせ配信", "ito@example.net", 12, 30, "todo", 0]]],
        ["結合テスト", "ito@example.net", 31, 48, "todo", 0],
        ["受入テスト", "admin@example.com", 49, 57, "todo", 0],
      ],
      milestone: ["本番リリース", 60],
    },
    // Scrum: sprints and tasks [title, assignee, points, status, sprint (0 closed, 1 active, null backlog)]
    scrum: {
      project: "mobile",
      sprints: [
        { name: "Sprint 1", goal: "ログインと店舗選択", starts: -21, ends: -8 },
        { name: "Sprint 2", goal: "シフト表を見られるようにする", starts: -7, ends: 6 },
      ],
      tasks: [
        ["ログイン画面", "takahashi@example.com", 3, "done", 0],
        ["店舗の選択", "takahashi@example.com", 5, "done", 0],
        ["プッシュ通知の基盤", "suzuki@example.com", 5, "done", 0],
        ["シフト表の一覧", "takahashi@example.com", 5, "done", 1],
        ["シフトの詳細", "takahashi@example.com", 3, "in_progress", 1],
        ["シフト変更の申請", "suzuki@example.com", 8, "in_progress", 1],
        ["オフライン時の表示", "takahashi@example.com", 3, "todo", 1],
        ["勤怠の打刻", null, 8, "todo", null],
        ["お知らせ一覧", null, 3, "todo", null],
      ],
    },
    maintenance: {
      project: "api",
      tasks: [["月次のバックアップ確認", "admin@example.com", 5, "todo"], ["ログ保管期間の変更依頼", "suzuki@example.com", 12, "in_progress"], ["CSV 出力の文字化け調査", "suzuki@example.com", -2, "done"]],
    },
    // Timesheet rows: [user, project key or null, task title or label, hours Mon..Fri per week (oldest first)]
    timesheet: [
      ["suzuki@example.com", "portal", "会員登録・ログイン", [[7, 7, 6, 7, 6], [6, 7, 7, 5, 7], [6, 6, 7, 0, 0]]],
      ["suzuki@example.com", null, "社内ミーティング", [[1, 1, 2, 1, 2], [2, 1, 1, 3, 1], [2, 1, 1, 0, 0]]],
      ["ito@example.net", "portal", "マイページ", [[0, 0, 0, 8, 8], [8, 8, 7, 8, 8], [8, 8, 8, 0, 0]]],
      ["ito@example.net", "portal", "画面設計", [[8, 8, 8, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]],
    ],
    personalTokens: [["Claude Desktop", "read"], ["Claude Code", "write"]],
    ciToken: "GitHub Actions",
    repo: { project: "portal", repo: "example/customer-portal" },
  },
  en: {
    roles: {
      "olivia@example.com": { roles: ["company_admin", "sales"], unit_cost: 60000 },
      "james@example.com": { unit_cost: 55000 },
      "emma@example.com": { unit_cost: 50000 },
      "noah@example.net": { unit_cost: 45000 },
    },
    customers: [
      { key: "minato", name: "Harbor Logistics Inc.", industry: "Logistics", address: "1-1 Kaigan-dori, Naka-ku, Yokohama", phone: "045-000-0000", payment_terms: "Net 30, end of month", contact: { name: "Naoki Yamamoto", title: "IT Manager", email: "yamamoto@harbor.example" } },
      { key: "sakura", name: "Sakura Realty Co.", industry: "Real estate", address: "2-2 Sakuragaoka, Shibuya, Tokyo", phone: "03-0000-0000", payment_terms: "Net 30, end of month", contact: { name: "Megumi Nakamura", title: "Corporate Planning", email: "nakamura@sakura.example" } },
      { key: "hokuto", name: "Polaris Manufacturing Ltd.", industry: "Manufacturing", address: "3-3 Nakamura-ku, Nagoya", phone: "052-000-0000", payment_terms: "Closing on the 20th, paid on the 20th of next month", contact: { name: "Daisuke Kato", title: "Head of Production Control", email: "kato@polaris.example" } },
    ],
    projects: {
      portal: { status: "development", method: "waterfall", customer: "minato", manager: "james@example.com", sales: "olivia@example.com", starts: -42, ends: 60 },
      api: { status: "maintenance" },
      mobile: { status: "development", method: "scrum", customer: "sakura", manager: "emma@example.com", sales: "olivia@example.com", starts: -35, ends: 90 },
      booking: { status: "development", method: "waterfall" },
    },
    deals: [
      { key: "production", name: "Production System Renewal", description: "Move factory planning and results tracking to the web", status: "negotiation", customer: "hokuto", expected_amount: 18000000, probability: 60, next_action: "Send the final proposal", next_action_on: 3 },
      { key: "search", name: "Property Search App", description: "Rental search and viewing booking app", status: "proposal", customer: "sakura", expected_amount: 6500000, probability: 40, next_action: "Submit a rough estimate", next_action_on: 7 },
      { key: "delivery", name: "Delivery App Update", description: "New features for the driver app", status: "inquiry", customer: "minato", expected_amount: 3000000, probability: 20 },
    ],
    estimates: {
      portal: [
        { title: "Customer Portal initial development", kind: "initial", amount: 9800000, status: "won", issued_on: -60, decided_on: -45, lines: [["Requirements and design", "james@example.com", 20], ["Frontend development", "noah@example.net", 40], ["Backend development", "james@example.com", 35], ["Testing", "noah@example.net", 20]], invoices: [["Down payment", -40, "paid"], ["Interim payment", -5, "invoiced"], ["On acceptance", 62, "planned"]] },
        { title: "Membership tiers (additional)", kind: "additional", amount: 1600000, status: "submitted", issued_on: -4, lines: [["Design", "james@example.com", 5], ["Development and testing", "noah@example.net", 15]] },
      ],
      production: [
        { title: "Production System Renewal (rough)", kind: "initial", amount: 18000000, status: "submitted", issued_on: -10, lines: [["Requirements", "olivia@example.com", 30], ["Design and development", "james@example.com", 180], ["Testing and migration", "emma@example.com", 60]] },
      ],
    },
    activities: {
      production: [
        { kind: "meeting", occurred_on: -14, participants: "Mr. Kato, Olivia", body: "Heard the issues with the current system. They want to drop paper work logs and link inventory with the production plan." },
        { kind: "email", occurred_on: -3, participants: "Mr. Kato", body: "Sent the rough estimate. They will discuss it internally next week.", next_action: "Send the final proposal", next_action_assignee: "olivia@example.com", next_action_due: 3 },
      ],
    },
    gantt: {
      portal: [
        ["Requirements", "james@example.com", -42, -29, "done", 100, [["Business interviews", "james@example.com", -42, -36, "done", 100], ["Requirements document", "james@example.com", -35, -29, "done", 100]]],
        ["Basic design", "james@example.com", -28, -15, "done", 100, [["Screen design", "noah@example.net", -28, -20, "done", 100], ["API design", "james@example.com", -24, -15, "done", 100]]],
        ["Development", "james@example.com", -14, 30, "in_progress", 30, [["Sign-up and login", "james@example.com", -14, 2, "in_progress", 70], ["My page", "noah@example.net", -4, 16, "in_progress", 20], ["Announcements", "noah@example.net", 12, 30, "todo", 0]]],
        ["Integration testing", "noah@example.net", 31, 48, "todo", 0],
        ["Acceptance testing", "admin@example.com", 49, 57, "todo", 0],
      ],
      milestone: ["Go-live", 60],
    },
    scrum: {
      project: "mobile",
      sprints: [
        { name: "Sprint 1", goal: "Login and store selection", starts: -21, ends: -8 },
        { name: "Sprint 2", goal: "Staff can see their shifts", starts: -7, ends: 6 },
      ],
      tasks: [
        ["Login screen", "emma@example.com", 3, "done", 0],
        ["Store selection", "emma@example.com", 5, "done", 0],
        ["Push notification setup", "james@example.com", 5, "done", 0],
        ["Shift list", "emma@example.com", 5, "done", 1],
        ["Shift details", "emma@example.com", 3, "in_progress", 1],
        ["Shift change requests", "james@example.com", 8, "in_progress", 1],
        ["Offline view", "emma@example.com", 3, "todo", 1],
        ["Time clock", null, 8, "todo", null],
        ["Announcement list", null, 3, "todo", null],
      ],
    },
    maintenance: {
      project: "api",
      tasks: [["Check the monthly backup", "admin@example.com", 5, "todo"], ["Change the log retention period", "james@example.com", 12, "in_progress"], ["Investigate garbled CSV export", "james@example.com", -2, "done"]],
    },
    timesheet: [
      ["james@example.com", "portal", "Sign-up and login", [[7, 7, 6, 7, 6], [6, 7, 7, 5, 7], [6, 6, 7, 0, 0]]],
      ["james@example.com", null, "Team meetings", [[1, 1, 2, 1, 2], [2, 1, 1, 3, 1], [2, 1, 1, 0, 0]]],
      ["noah@example.net", "portal", "My page", [[0, 0, 0, 8, 8], [8, 8, 7, 8, 8], [8, 8, 8, 0, 0]]],
      ["noah@example.net", "portal", "Screen design", [[8, 8, 8, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]],
    ],
    personalTokens: [["Claude Desktop", "read"], ["Claude Code", "write"]],
    ciToken: "GitHub Actions",
    repo: { project: "portal", repo: "example/customer-portal" },
  },
};
