# Vectana MCP サーバ

Claude などの AI クライアントから Vectana を操作するための [MCP](https://modelcontextprotocol.io/) サーバです（stdio）。Vectana の REST API を、発行したユーザー本人の権限で呼び出します。

## できること

| 機能 | 主なツール |
|---|---|
| アカウント | `whoami` `search_users` |
| ダッシュボード | `get_dashboard` `get_org_dashboard` |
| 脆弱性・トリアージ | `list_vulnerabilities` `get_vulnerability` `update_vulnerability` `comment_vulnerability` |
| パッケージ・SBOM | `list_packages` `add_package` `import_dependencies` `scan_project` |
| EOL | `list_eol` `list_runtimes` `search_eol_products` `add_runtime` |
| プロジェクト・商談 | `list_projects` `get_project` `create_project` `update_project` `list_project_members` `add_project_member` |
| 顧客 | `list_customers` `get_customer` `create_customer` `update_customer` `add_customer_contact` |
| 見積 | `list_estimates` `get_estimate` `create_estimate` `update_estimate` |
| タスク | `list_my_tasks` `list_project_tasks` `get_task` `create_task` `update_task` `list_security_candidates` `create_security_task` |
| スプリント | `list_sprints` `get_burndown` `get_velocity` `create_sprint` `update_sprint` |
| 実績工数 | `get_timesheet` `log_time` `save_timesheet` `submit_timesheet` `get_project_actuals` |
| 商談メモ | `list_activities` `add_activity` `update_activity` |
| 請求 | `list_project_invoices` `list_invoices` `plan_invoices` `update_invoice` |
| リポジトリ連携 | `list_repo_links` `import_from_repo` `sync_repo_issues` |

削除系の操作は、AI が誤って消さないよう用意していません（画面から行ってください）。

`import_dependencies` は、MCP サーバが動いているマシン上のファイルパス（例: `./package-lock.json`）を渡すとそのまま取り込みます。

## 使い方

1. Vectana の「個人設定 → 個人用トークン」でトークン（`vcu_...`）を発行します。読み取り専用にすると、閲覧だけで変更はできません。
2. MCP クライアントに登録します。

Claude Desktop など（`claude_desktop_config.json`）:

```json
{
  "mcpServers": {
    "vectana": {
      "command": "npx",
      "args": ["-y", "@techolve/vectana-mcp"],
      "env": {
        "VECTANA_URL": "https://vectana.example.com",
        "VECTANA_TOKEN": "vcu_..."
      }
    }
  }
}
```

Claude Code:

```bash
claude mcp add vectana -e VECTANA_URL=https://vectana.example.com -e VECTANA_TOKEN=vcu_... -- npx -y @techolve/vectana-mcp
```

npm に公開する前やソースから使う場合は、ビルドして `node` で起動します。

```bash
cd mcp && npm ci && npm run build
# command: "node", args: ["/path/to/vectana/mcp/dist/index.js"]
```

### 環境変数

| 変数 | 内容 |
|---|---|
| `VECTANA_URL` | Vectana の URL（必須） |
| `VECTANA_TOKEN` | 個人用トークン（必須） |
| `VECTANA_LOCALE` | `ja` / `en`。エラーメッセージの言語 |
| `VECTANA_READ_ONLY` | `1` にすると読み取り系のツールだけを公開する |

## 開発

```bash
mise run mcp:install   # 依存関係
mise run mcp:test      # テスト
mise run mcp:lint      # 型チェック
mise run mcp:build     # dist/ にビルド
mise run mcp:types     # API の OpenAPI から src/api-types.ts を作り直す
```

- ツールは機能ごとに `src/tools/<機能>.ts` に書き、`src/tools/index.ts` に追加します。
- 列挙値は `apiEnum<Schemas["..."]>()` で書くと、API 側に値が増えたときに型チェックで気づけます。
- API を変えたら `mise run mcp:types` を実行してください。CI は `src/api-types.ts` が最新かを確認します。

## npm への公開

`@techolve/vectana-mcp` として npm に公開します。

1. 初回だけ手元で公開します（npm の `techolve` Organization のメンバーで、2 段階認証が必要）。`prepack` でビルドと LICENSE のコピーが走ります。

   ```bash
   cd mcp && npm ci && npm login && npm publish
   ```

2. npmjs.com のパッケージ設定 → Trusted Publisher で、GitHub Actions・`techolve/vectana`・ワークフロー `mcp-publish.yml` を登録します。
3. 以降は `mcp/package.json` の `version` を上げてマージし、`mcp-v<version>` のタグを push すると [Publish MCP server](../.github/workflows/mcp-publish.yml) が公開します（npm トークンは不要です）。

   ```bash
   git tag mcp-v1.1.1 && git push origin mcp-v1.1.1
   ```

