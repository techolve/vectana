# Vectana

工数管理・脆弱性監視プラットフォーム。プロジェクト情報を一元管理し、開発業務に必要な情報を集約することを目指す。

## 構成

Vectanaは複数リポジトリで構成されています。

| リポジトリ                                               | 役割                                                    |
| -------------------------------------------------------- | ------------------------------------------------------- |
| [vectana](https://github.com/techolve/vectana)           | docker-compose によるセルフホスト入口（このリポジトリ） |
| [vectana-api](https://github.com/techolve/vectana-api)   | バックエンド（FastAPI）                                 |
| [vectana-web](https://github.com/techolve/vectana-web)   | フロントエンド（Next.js）                               |
| [vectana-docs](https://github.com/techolve/vectana-docs) | ドキュメント（Zensical）                                |

## セットアップ

```bash
docker compose up
```

## ライセンス

検討中。
