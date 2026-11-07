"""Server-side translations (ja / en).

API errors are raised in English and translated on the way out according to
the request's ``Accept-Language`` (the web app sends its current locale).
Emails and webhook digests use the recipient's saved locale.
"""

import re
from typing import Any

from starlette.requests import Request

LOCALES = ("ja", "en")
DEFAULT_LOCALE = "ja"


def normalize(locale: str | None) -> str:
    """Map "en-US", "ja;q=0.9" etc. to a supported locale."""
    if locale:
        tag = locale.split(",")[0].split(";")[0].strip().lower()[:2]
        if tag in LOCALES:
            return tag
    return DEFAULT_LOCALE


def request_locale(request: Request) -> str:
    return normalize(request.headers.get("accept-language"))


# --- API errors --------------------------------------------------------------

ERRORS_JA: dict[str, str] = {
    "A department cannot be its own ancestor": "部署を自分の配下に移動することはできません",
    "Account is disabled": "このアカウントは無効化されています",
    "Administrator access required": "管理者権限が必要です",
    "Already a member": "すでにメンバーです",
    "Assignee cannot triage this project": (
        "このユーザーはこのプロジェクトの脆弱性対応を行えません（閲覧のみ・未アサイン）"
    ),
    "Assignee not found": "担当者が見つかりません",
    "Cannot modify a group admin": "グループ管理者は変更できません",
    "Company name already exists": "同じ名前の会社がすでにあります",
    "Comment not found": "コメントが見つかりません",
    "Company not found": "会社が見つかりません",
    "Company still has users or projects": "ユーザーかプロジェクトが残っているため削除できません",
    "Current password is wrong": "現在のパスワードが違います",
    "Delete sub-departments first": "先に配下の部署を削除してください",
    "Demote this company's administrators before making it a partner": (
        "BPに変更する前に、この会社の管理者をメンバーに変更してください"
    ),
    "Department already exists here": "同じ場所に同じ名前の部署がすでにあります",
    "Department must be in the same company": "部署はプロジェクトと同じ会社のものを選んでください",
    "Department not found": "部署が見つかりません",
    "Departments must belong to the user's company": (
        "部署はユーザーと同じ会社のものを選んでください"
    ),
    "Email already registered": "このメールアドレスはすでに登録されています",
    "File too large": "ファイルが大きすぎます",
    "Group administrator required": "グループ管理者の権限が必要です",
    "API token has expired": "APIトークンの有効期限が切れています",
    "Insufficient permission": "権限がありません",
    "Invalid credentials": "メールアドレスまたはパスワードが違います",
    "Invalid API token": "APIトークンが正しくありません",
    "Invalid token": "認証情報が正しくありません",
    "Invalid token type": "認証情報が正しくありません",
    "This token is read-only": "このトークンは読み取り専用です",
    "Personal tokens cannot manage tokens": "個人用トークンではトークンを管理できません",
    "Invalid assignee": "担当者の指定が正しくありません",
    "Invitation has expired": "招待の有効期限が切れています",
    "Invitation not found": "招待が見つかりません",
    "Member not found": "メンバーが見つかりません",
    "Not allowed for this company": "この会社に対する操作は許可されていません",
    "Not available for partner users": "BP（協力会社）のユーザーは利用できません",
    "Not found": "見つかりません",
    "Only group admins can grant this role": "このロールはグループ管理者だけが付与できます",
    "Only one primary department allowed": "主所属にできる部署は1つだけです",
    "Package already registered": "このパッケージはすでに登録されています",
    "Package not found": "パッケージが見つかりません",
    "Parent must be in the same company": "親部署は同じ会社のものを選んでください",
    "Partner users can only be members": "BP（協力会社）のユーザーはメンバーにしかできません",
    "Partner users cannot be project owners": "BP（協力会社）のユーザーはオーナーにできません",
    "Partner users cannot create projects": (
        "BP（協力会社）のユーザーはプロジェクトを作成できません"
    ),
    "Project not found": "プロジェクトが見つかりません",
    "Projects belong to a group company": "プロジェクトはグループ内の会社に作成してください",
    "Runtime already registered": "このランタイムはすでに登録されています",
    "Runtime not found": "ランタイムが見つかりません",
    "Token has expired": "ログインの有効期限が切れました",
    "Token not found": "APIトークンが見つかりません",
    "Unknown status": "対応状況の指定が正しくありません",
    "Unknown product": "endoflife.date に登録されていない製品です",
    "Unknown severity": "重大度の指定が正しくありません",
    "User has no company": "ユーザーが会社に所属していません",
    "User not found": "ユーザーが見つかりません",
    "Webhook not found": "Webhook が見つかりません",
    "You cannot change your own role or disable yourself": (
        "自分自身のロール変更や無効化はできません"
    ),
    "company_id is required": "会社を指定してください",
    "source must be 1-80 characters of letters, digits and ._/@+-": (
        "取り込み元の名前は英数字と ._/@+- で80文字以内にしてください"
    ),
    "Invalid request": "入力内容が正しくありません",
}

# Messages with a variable part: (pattern, Japanese template using the groups).
PATTERNS_JA: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Webhook failed: (.*)$"), r"Webhook の送信に失敗しました: \1"),
    (
        re.compile(r"^Unsupported file '(.*)'\. Supported: (.*)$"),
        r"対応していないファイルです（\1）。対応形式: \2",
    ),
    (re.compile(r"^Could not parse (.*?): (.*)$"), r"\1 を読み込めませんでした: \2"),
]


def translate_error(message: str, locale: str) -> str:
    if locale != "ja":
        return message
    if message in ERRORS_JA:
        return ERRORS_JA[message]
    for pattern, template in PATTERNS_JA:
        if pattern.match(message):
            return pattern.sub(template, message)
    return message


def validation_message(errors: list[dict[str, Any]], locale: str) -> str:
    """One readable line for a 422 from request validation."""
    fields = []
    for e in errors:
        loc = [str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path")]
        reason = str(e.get("msg", "")).removeprefix("Value error, ")
        fields.append(f"{'.'.join(loc) or 'request'}: {reason}")
    head = "入力内容が正しくありません" if locale == "ja" else "Invalid request"
    return f"{head} ({'; '.join(fields)})" if fields else head


# --- Emails and digests --------------------------------------------------------

TEXTS: dict[str, dict[str, str]] = {
    "invite.subject": {"ja": "[Vectana] アカウント招待", "en": "[Vectana] You're invited"},
    "invite.body": {
        "ja": "{company} のメンバーとして Vectana に招待されました。",
        "en": "You have been invited to Vectana as a member of {company}.",
    },
    "invite.action": {"ja": "パスワードを設定する", "en": "Set your password"},
    "invite.link_hint": {
        "ja": "次のリンクからパスワードを設定してください（有効期限 {days} 日）:",
        "en": "Set your password with the link below (valid for {days} days):",
    },
    "invite.fallback": {
        "ja": "リンクが開けない場合は次のURLをブラウザに貼り付けてください:",
        "en": "If the button doesn't work, paste this URL into your browser:",
    },
    "invite.ignore": {
        "ja": "心当たりがない場合はこのメールを無視してください。",
        "en": "If you weren't expecting this, you can ignore this email.",
    },
    "digest.subject": {
        "ja": "[Vectana] 対応が必要な項目が {count} 件あります",
        "en": "[Vectana] {count} item(s) need your attention",
    },
    "digest.vulns": {"ja": "新しい脆弱性（{count} 件）", "en": "New vulnerabilities ({count})"},
    "digest.eol": {"ja": "サポート終了（EOL）（{count} 件）", "en": "End of life ({count})"},
    "digest.more": {"ja": "…ほか {count} 件", "en": "…and {count} more"},
    "digest.dashboard": {"ja": "ダッシュボード", "en": "Dashboard"},
    "digest.open": {"ja": "Vectana を開く", "en": "Open Vectana"},
    "digest.col.severity": {"ja": "重大度", "en": "Severity"},
    "digest.col.project": {"ja": "プロジェクト", "en": "Project"},
    "digest.col.package": {"ja": "パッケージ", "en": "Package"},
    "digest.col.fixed": {"ja": "修正版", "en": "Fixed in"},
    "digest.col.vuln": {"ja": "脆弱性", "en": "Vulnerability"},
    "digest.col.product": {"ja": "製品", "en": "Product"},
    "digest.col.status": {"ja": "状態", "en": "Status"},
    "digest.col.eol_date": {"ja": "EOL日", "en": "EOL date"},
    "eol.status.eol": {"ja": "サポート終了", "en": "End of life"},
    "eol.status.approaching": {"ja": "まもなく終了", "en": "Ending soon"},
    "eol.latest": {"ja": "（最新 {version}）", "en": " (latest {version})"},
    "eol.line.eol": {"ja": "{date} にサポート終了", "en": "ended on {date}"},
    "eol.line.approaching": {"ja": "{date} にサポート終了予定", "en": "ends on {date}"},
    "report.unassigned": {"ja": "（部署未設定）", "en": "(No department)"},
    "report.col.company": {"ja": "会社", "en": "Company"},
    "report.col.department": {"ja": "部署", "en": "Department"},
    "report.col.projects": {"ja": "プロジェクト数", "en": "Projects"},
    "report.col.critical": {"ja": "CRITICAL", "en": "CRITICAL"},
    "report.col.high": {"ja": "HIGH", "en": "HIGH"},
    "report.col.medium": {"ja": "MEDIUM", "en": "MEDIUM"},
    "report.col.low": {"ja": "LOW", "en": "LOW"},
    "report.col.unknown": {"ja": "UNKNOWN", "en": "UNKNOWN"},
    "report.col.overdue": {"ja": "期限超過", "en": "Overdue"},
    "report.col.oldest_overdue_days": {
        "ja": "最長超過日数",
        "en": "Longest overdue (days)",
    },
    "report.col.eol": {"ja": "EOL到達", "en": "EOL reached"},
    "report.col.eol_approaching": {"ja": "EOL接近", "en": "EOL approaching"},
    "report.col.nearest_eol_date": {"ja": "直近のEOL日", "en": "Nearest EOL date"},
    "report.col.nearest_eol_days": {"ja": "EOLまでの日数", "en": "Days to EOL"},
    "report.col.partial": {"ja": "一部のみ", "en": "Partial"},
    "report.col.unit": {"ja": "会社・部署", "en": "Company / department"},
    "report.col.open": {"ja": "未対応", "en": "Open"},
    "report.col.due": {"ja": "期限", "en": "Due"},
    "report.col.days_over": {"ja": "超過日数", "en": "Days over"},
    "report.col.days_left": {"ja": "残り日数", "en": "Days left"},
    "report.subject": {
        "ja": "[Vectana] 週次レポート（{period}）期限超過 {overdue} 件",
        "en": "[Vectana] Weekly report ({period}): {overdue} overdue",
    },
    "report.intro": {
        "ja": "{scope} の脆弱性とEOLの状況です（{today} 時点）。",
        "en": "Vulnerability and EOL status for {scope} as of {today}.",
    },
    "report.summary": {
        "ja": (
            "プロジェクト {projects} 件 / 未対応の脆弱性 {open} 件"
            "（CRITICAL {critical}、HIGH {high}）/ 期限超過 {overdue} 件 / "
            "EOL到達 {eol} 件・接近 {approaching} 件"
        ),
        "en": (
            "{projects} projects / {open} open vulnerabilities "
            "(CRITICAL {critical}, HIGH {high}) / {overdue} overdue / "
            "EOL reached {eol}, approaching {approaching}"
        ),
    },
    "report.units": {"ja": "会社・部署別", "en": "By company and department"},
    "report.overdue": {
        "ja": "期限超過の脆弱性（古い順、上位 {count} 件）",
        "en": "Overdue vulnerabilities (oldest first, top {count})",
    },
    "report.upcoming_eol": {
        "ja": "EOLが近いもの（上位 {count} 件）",
        "en": "Nearest EOL (top {count})",
    },
    "report.none": {"ja": "なし", "en": "None"},
    "report.days_left": {"ja": "あと {days} 日", "en": "in {days} days"},
    "report.days_over": {"ja": "{days} 日超過", "en": "{days} days ago"},
    "report.open_link": {
        "ja": "組織別ダッシュボードを開く",
        "en": "Open the organization dashboard",
    },
    "report.scope.group": {"ja": "グループ全体", "en": "the whole group"},
    "report.scope.mine": {"ja": "あなたの担当範囲", "en": "your organization"},
    "report.partial_note": {
        "ja": "* はあなたに見えるプロジェクトだけの集計です。",
        "en": "* covers only the projects you can see.",
    },
    "test.subject": {"ja": "[Vectana] テスト通知", "en": "[Vectana] Test notification"},
    "test.body": {
        "ja": "Vectana からのテスト通知です。この通知が届いていれば設定は正しく動いています。",
        "en": "This is a test notification from Vectana. If you can read this, it works.",
    },
}


def t(locale: str, key: str, **kwargs: object) -> str:
    entry = TEXTS[key]
    return entry.get(locale, entry[DEFAULT_LOCALE]).format(**kwargs)
