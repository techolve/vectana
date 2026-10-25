# Vectana

📖 ドキュメント（日本語 / English）: https://docs.vectana.techolve.org

プロジェクトごとに使っているパッケージを登録しておくと、[OSV](https://osv.dev/) で脆弱性を定期チェックして、メールと Discord / Slack に通知するアプリです。

- 組織: グループ > 会社（親会社・関連会社・BP）> 部署（入れ子）
- 権限: グループ管理者 / 会社管理者 / 部署長（配下の部署のプロジェクト）/ メンバーと BP（アサインされたプロジェクトだけ）
- パッケージ登録: 手入力、または lockfile の取り込み（`package-lock.json` `pnpm-lock.yaml` `uv.lock` `poetry.lock` `requirements*.txt` `pubspec.lock`）

## 構成

| パス | 内容 |
|---|---|
| `api/` | FastAPI。API と worker（`python -m app.worker`）を含む |
| `web/` | Next.js（静的書き出し）。ビルドしたものを FastAPI が配信する |
| `docker/Dockerfile` | アプリのイメージ（1つ）|
| `compose.yaml` | ローカル用（db / migrate / app / worker / mailpit）|
| `compose.prod.yaml` | 本番用（Docker Hub のイメージを使う）|

## ローカルで動かす

```bash
docker compose --profile dev up -d --build
docker compose exec app python -m app.cli create-admin --email you@example.com --company "親会社名"
```

- アプリ: http://localhost:8000
- 送信されたメール（Mailpit）: http://localhost:8025
- API ドキュメント: http://localhost:8000/api/docs
- 手動でスキャンを1回実行: `docker compose run --rm worker python -m app.worker --once`

## 開発

ツールのバージョンとタスクは [mise](https://mise.jdx.dev/) で管理しています（`mise.toml`）。

```bash
mise trust && mise install   # Python / Node.js / uv / git-cliff を入れる
mise run setup               # api と web の依存関係を入れる
mise run services            # PostgreSQL と Mailpit を Docker で起動
mise run migrate             # DB を最新にする
mise run dev                 # API (:8000) と web (:3100) を起動
```

よく使うタスク:

| タスク | 内容 |
|---|---|
| `mise run check` | lint・テスト・web のビルド（CI と同じ） |
| `mise run api:test` | API のテスト |
| `mise run api:worker` | スキャンを1回実行 |
| `mise run makemigration -- "message"` | マイグレーションを自動生成 |
| `mise run changelog -- --tag vX.Y.Z` | CHANGELOG.md を更新 |
| `mise tasks` | タスクの一覧 |

本番へのデプロイは [docs/deploy.md](docs/deploy.md) を参照。

## ライセンス

[AGPL-3.0](LICENSE)
