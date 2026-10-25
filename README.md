# Vectana

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

```bash
cd api && uv sync && uv run pytest        # API
cd web && npm install && npm run dev      # web（/api は localhost:8000 にプロキシ）
```

本番へのデプロイは [docs/deploy.md](docs/deploy.md) を参照。

## ライセンス

[AGPL-3.0](LICENSE)
