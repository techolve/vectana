// Fictional demo data for documentation screenshots. Same shape per locale so
// the English screenshots show English names. Package versions are picked to
// hit known OSV advisories and endoflife.date cycles.

export const ADMIN_EMAIL = "admin@example.com";
export const ADMIN_PASSWORD = "vectana-demo-admin";
export const USER_PASSWORD = "vectana-demo-user";

const packages = {
  portal: [
    ["npm", "next", "16.4.3"],
    ["npm", "react", "19.2.4"],
    ["npm", "form-data", "4.0.0"],
    ["npm", "jsonwebtoken", "8.5.1"],
    ["npm", "lodash", "4.17.20"],
    ["npm", "dayjs", "1.11.13"],
  ],
  api: [
    ["PyPI", "django", "6.1.2"],
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
        members: [["takahashi@example.com", "owner"], ["suzuki@example.com", "viewer"]],
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
        members: [["emma@example.com", "owner"], ["james@example.com", "viewer"]],
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
