# rag-support-assist ドキュメント目次

`docs/` 配下のドキュメントを目的別に俯瞰するためのインデックスです。ルート [`../README.md`](../README.md) は「rag-support-assist とは何か / どう動かすか」の入り口、こちらは「何か知りたい・調べたい」ときの導線として機能します。

## 目的別ガイド

| やりたいこと | 参照先 |
| --- | --- |
| REST API の仕様・エンドポイント・リクエスト/レスポンス例を確認したい | [`API.md`](API.md) |
| システム全体像・サービス責務・データフローを把握したい | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 環境変数・設定項目・チューニングポイントを調べたい | [`CONFIGURATION.md`](CONFIGURATION.md) |
| RAG のシステムプロンプト・トーン切替・エスカレーション判定プロンプトの設計意図と変更時の注意を知りたい | [`PROMPT_GUIDELINES.md`](PROMPT_GUIDELINES.md) |
| 回答品質の評価（Eval）方針・実行手順・指標を知りたい | [`EVAL.md`](EVAL.md) |
| 症状から障害切り分け手順を辿りたい・エラー時の対処を調べたい | [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) |

## 初めての方向け

初めて rag-support-assist に触れる場合は、以下の順序で読むことを推奨します。

1. ルート [`../README.md`](../README.md) — プロジェクト概要・クイックスタート・利用例
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — backend (Python) / frontend の全体構成、RAG パイプラインの流れを把握
3. [`CONFIGURATION.md`](CONFIGURATION.md) — 環境変数と設定の全体像
4. [`API.md`](API.md) — 実際に API を叩くときのリファレンス
5. [`PROMPT_GUIDELINES.md`](PROMPT_GUIDELINES.md) — 回答生成プロンプトの設計思想と変更時のチェックリスト
6. [`EVAL.md`](EVAL.md) — 回答品質を評価・回帰する仕組みを知る
7. [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 詰まったときのリファレンス

## リポジトリ全体のガイド

`docs/` 以外にも、以下のリポジトリルート直下のドキュメントが対応するテーマを扱っています。

| テーマ | 参照先 |
| --- | --- |
| コントリビュート方針・PR / Issue 作成手順・開発フロー | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| コミュニティ規範（Contributor Covenant 準拠） | [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) |
| 脆弱性報告経路・サポート対象バージョン | [`../SECURITY.md`](../SECURITY.md) |
| 変更履歴（Keep a Changelog 形式） | [`../CHANGELOG.md`](../CHANGELOG.md) |
| バックエンド（Python / FastAPI） | [`../backend/`](../backend/) |
| フロントエンド（Next.js / TypeScript） | [`../frontend/`](../frontend/) |
| Docker Compose による構成起動 | [`../docker-compose.yml`](../docker-compose.yml) |

## 新しいドキュメントを追加する場合

- **プロジェクト全体に関するもの**（コントリビュート方針、セキュリティ方針、変更履歴、リリース手順など）はリポジトリルート直下に置きます。
- **開発・運用・障害対応のリファレンス**（アーキテクチャ図、機能設計、API 仕様、評価方針、トラブルシューティング手順など）は `docs/` 配下に置きます。
- 新しいファイルを `docs/` に追加した場合は、本ファイルの「目的別ガイド」表にエントリを追加し、目的（読み手が「何を知りたい」ときに参照するのか）を 1 行で書き添えてください。
- 命名は原則 `UPPER_SNAKE_CASE.md`（既存 `API.md` / `ARCHITECTURE.md` などに合わせる）とします。単一名詞または短いフレーズを推奨。
- ドキュメント間の関係は、必要に応じて「関連ドキュメント」節で相互リンクしてください。
