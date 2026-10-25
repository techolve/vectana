# デプロイ手順（VPS + Cloudflare Tunnel）

## 1. イメージを Docker Hub に push（手元で実行）

`techolve/vectana` は **Private** リポジトリ。VPS は amd64 なので、マルチアーキテクチャでビルドする。

```bash
docker login
docker buildx build --platform linux/amd64,linux/arm64 -f docker/Dockerfile \
  -t techolve/vectana:0.1.0 -t techolve/vectana:latest --push .
```

## 2. VPS で起動

```bash
mkdir -p ~/vectana && cd ~/vectana
# compose.prod.yaml と .env.example をコピーしてくる
cp .env.example .env   # POSTGRES_PASSWORD / SECRET_KEY / WEB_URL / メール設定を埋める
docker login           # Private イメージを pull するため
docker compose -f compose.prod.yaml up -d
docker compose -f compose.prod.yaml exec app python -m app.cli create-admin --email you@example.com --company "親会社名"
```

`SECRET_KEY` は `openssl rand -hex 32` で生成する。未設定だとアプリが起動しない。

## 3. Cloudflare Tunnel

cloudflared の `config.yml` の `ingress` に、既存の gitlab / redmine の行と同じ形で追加して再起動する。

```yaml
  - hostname: vectana.example.com
    service: http://localhost:8000
```

`WEB_URL` は `https://vectana.example.com` にする（招待メールや通知のリンクに使われる）。

## 4. メール（Cloudflare）

- **受信**: Email Routing で `vectana@<ドメイン>` を普段使っているメールアドレスに転送する。返信やバウンスもそこで読める
- **送信**: Cloudflare Email Service（ベータ版）。任意の宛先に送るには **Workers Paid プラン** が必要。ダッシュボードで送信ドメインを認証してから、次のどちらかを設定する
  - REST API: `MAIL_BACKEND=cloudflare`、`CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN`（メール送信の権限を付けたトークン）、`MAIL_FROM=vectana@<ドメイン>`
  - SMTP: `MAIL_BACKEND=smtp`、`SMTP_HOST=smtp.mx.cloudflare.net`、`SMTP_PORT=465`、`SMTP_USE_TLS=true`、ユーザー名とパスワードは Cloudflare の SMTP 設定画面で確認する
- Workers Paid にしない場合は、Resend などの SMTP リレーを `MAIL_BACKEND=smtp` で使う（DNS は Cloudflare に登録する）
- メールの準備ができるまでは `MAIL_BACKEND=none` にしておけば起動できる。その場合、招待は管理画面に表示されるリンクを直接共有する

## 5. 確認

- `https://vectana.example.com/api/health` が `{"status":"ok"}` を返す
- `docker compose -f compose.prod.yaml logs worker` に `Scanned ... package(s)` が出ている
- バックアップ: `docker compose -f compose.prod.yaml exec db pg_dump -U vectana vectana > backup.sql`
