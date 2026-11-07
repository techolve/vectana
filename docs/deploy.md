# デプロイ手順（Cloudflare Containers）

メンテナー向けのリリース手順。利用者向けのインストール手順（Docker Compose でのセルフホスト）は https://docs.vectana.techolve.org/self-hosting/install にまとめてある。

techolve の本番（https://vectana.techolve.org）は Cloudflare Containers で動いている。

```
User ──HTTPS──▶ Worker ──▶ App コンテナ（uvicorn: API + Next.js の静的ファイル）──▶ PostgreSQL
                  │
                  └─ Cron ─▶ Scan コンテナ（python -m app.worker --once）──▶ OSV.dev / endoflife.date
                                                                          └▶ メール / Discord / Slack
```

- Worker と Containers の設定は、このリポジトリではなく techolve のインフラ用リポジトリ（techolve-cloud、非公開）の `vectana/` にある
- App と Scan は同じイメージ `heki0824/vectana` から起動する。違うのは起動コマンドだけ
- コンテナはどちらも寝かせる前提（`sleepAfter`）。App は Worker への HTTP で、Scan は Cron Trigger（6時間ごと）で起きる。Scan は `--once` で1回まわしたら終わる（期限が来ていればリポジトリ連携の取り込み → スキャン → 週次レポート）
- GitHub・GitLab の Webhook（`/api/repo-hooks/*`）も Worker 経由で App に届く。Cloudflare Access などで `/api/` を保護する場合は、このパスを除外する
- コンテナのディスクは使い捨て。状態は全部 PostgreSQL（PlanetScale Postgres）に置く

## 1. リリース（タグを打つと自動で公開）

1. バージョンを上げる PR を作る: `api/pyproject.toml` `api/app/__init__.py` `api/uv.lock` `web/package.json`（と lock）、MCP を出すなら `mcp/package.json`（と lock）と `mcp/src/server.ts`。CHANGELOG も更新する（`mise run changelog -- --tag vX.Y.Z` で下書きして整える）
2. マージしたら main にタグを打つ

```bash
git tag vX.Y.Z && git push origin vX.Y.Z          # Docker Hub（.github/workflows/docker-publish.yml）
git tag mcp-vX.Y.Z && git push origin mcp-vX.Y.Z  # npm（.github/workflows/mcp-publish.yml）
```

- `vX.Y.Z` で `heki0824/vectana:X.Y.Z` と `:latest` を linux/amd64・linux/arm64 で push する。リポジトリの Secrets に `DOCKERHUB_USERNAME`（heki0824）と `DOCKERHUB_TOKEN`（Docker Hub の Access Token、Read & Write）が必要
- `mcp-vX.Y.Z` で `@techolve/vectana-mcp` を npm に公開する（Trusted Publishing。トークン不要）
- どちらもタグとバージョンが合わないと失敗する

手元から push する場合（ワークフローが使えないとき）:

```bash
docker login -u heki0824
docker buildx build --platform linux/amd64,linux/arm64 -f docker/Dockerfile \
  -t heki0824/vectana:X.Y.Z -t heki0824/vectana:latest --push .
```

## 2. マイグレーション（スキーマが変わったときだけ）

Containers には compose の `migrate` サービスにあたるものがないので、手元から本番 DB に向けて流す。新しいイメージをデプロイする**前**にやる。

```bash
docker run --rm \
  -e DATABASE_URL='postgresql+asyncpg://<user>:<password>@<host>:5432/vectana?ssl=verify-full' \
  -e PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt \
  heki0824/vectana:X.Y.Z alembic upgrade head
```

## 3. Worker をデプロイ（techolve-cloud で実行）

`vectana/wrangler.jsonc` の `containers[].image` を2つとも新しいタグに上げてデプロイする。

```bash
npx wrangler deploy -c vectana/wrangler.jsonc --secrets-file ~/.config/techolve/secrets/vectana.json
```

- 秘密情報（`DB_USER` `DB_PASSWORD` `SECRET_KEY` `CLOUDFLARE_API_TOKEN` `OIDC_CLIENT_SECRET`）はリポジトリに置かず、secrets ファイルから渡す
- Worker が環境変数を組み立ててコンテナに渡す。`DATABASE_URL` は `?ssl=verify-full` 付きで、asyncpg が CA を見つけられるように `PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt` も渡す
- **環境変数だけを変えたとき**は、コンテナのインスタンス名を変えないと古い環境変数のまま動き続ける

## 4. 環境変数

| 変数 | 内容 |
|---|---|
| `DATABASE_URL` | PostgreSQL の接続先（Worker が `DB_HOST` `DB_NAME` `DB_USER` `DB_PASSWORD` から組み立てる） |
| `SECRET_KEY` | JWT の署名鍵。`openssl rand -hex 32` で生成する。未設定だとアプリが起動しない |
| `WEB_URL` | 公開 URL。招待メールや通知のリンクに使われる |
| `GROUP_NAME` | グループ名 |
| `REPORT_TIMEZONE` / `REPORT_HOUR` | 週次の組織レポートを送る時間帯（既定 `Asia/Tokyo` の 9 時以降）。曜日とオン/オフは管理画面で設定する |
| `MAIL_BACKEND` / `MAIL_FROM` | メール送信（下記） |
| `OIDC_*` | SSO（下記） |

### メール

- **送信**: Cloudflare Email Sending の REST API を使う。`MAIL_BACKEND=cloudflare`、`CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN`（メール送信の権限を付けたトークン）、`MAIL_FROM=Vectana <no-reply@<ドメイン>>`。送信ドメインはダッシュボードで認証しておく。任意の宛先に送るには Workers Paid プランが必要
- **受信**: Email Routing で、返信やバウンスを普段のメールアドレスに転送する
- Containers は SMTP を受けられないので、自前のメールサーバーは使えない。SMTP リレー（Resend など）を使うなら `MAIL_BACKEND=smtp` と `SMTP_*` を設定する
- メールの準備ができるまでは `MAIL_BACKEND=none` でも起動できる。その場合、招待は管理画面に表示されるリンクを直接共有する

### SSO（任意）

OpenID Connect に対応した ID プロバイダーがあれば、ログイン画面に「〇〇 でログイン」ボタンを出せる。アカウントは今までどおり招待で作り、SSO は**メールアドレスが一致する既存ユーザー**をログインさせるだけ。

- プロバイダーに登録するリダイレクト URI: `https://vectana.example.com/api/auth/oidc/callback`
- スコープ: `openid email profile`
- `OIDC_ISSUER`（`/.well-known/openid-configuration` の手前まで）、`OIDC_CLIENT_ID`、`OIDC_CLIENT_SECRET`、`OIDC_PROVIDER_NAME`（ボタンの表示名）を設定する
- techolve の本番は Cloudflare Access を使っている。Zero Trust で「SaaS アプリケーション」→「OIDC」を作る。`OIDC_ISSUER` は `https://<チーム名>.cloudflareaccess.com/cdn-cgi/access/sso/oidc/<クライアント ID>`

## 5. 最初の管理者（初回だけ）

手元から本番 DB に向けて実行する。

```bash
docker run --rm -e DATABASE_URL=... -e PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt \
  -e SECRET_KEY=... heki0824/vectana:X.Y.Z \
  python -m app.cli create-admin --email you@example.com --company "親会社名"
```

## 6. 確認

- `/api/health` は DB を使わないので、これだけでは DB 接続を確認できない。DB を使うエンドポイントも叩く（例: 間違ったパスワードで `POST /api/auth/login` して 401 が返る）
- スキャン: `npx wrangler tail techolve-vectana` で Cron の起動を見て、Cloudflare ダッシュボードの Containers のログに `Scanned ... package(s)` が出ていることを確認する
- バックアップ: PlanetScale のバックアップに加えて、必要なら手元から `pg_dump` を取る
