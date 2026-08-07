# Changelog

このプロジェクトの主な変更点を記録するファイルです。

フォーマットは [Keep a Changelog v1.1.0](https://keepachangelog.com/ja/1.1.0/) に、
バージョン番号は [Semantic Versioning](https://semver.org/lang/ja/) に準拠します。

## [Unreleased]

### Added

- （次回リリースで追加する機能をここに記載）

### Changed

- （挙動の変更をここに記載）

### Deprecated

- （非推奨になった機能をここに記載）

### Removed

- （削除された機能をここに記載）

### Fixed

- （バグ修正をここに記載）

### Security

- （セキュリティ関連の修正をここに記載）

## [0.1.0] - 2026-03-30

初回リリース。カスタマーサポート回答支援 AI (RAG) の Baseline 実装を記録します。

### Added

- **backend/**: FastAPI + Uvicorn による RAG クエリ API。埋め込み・ベクトル
  ストア連携・検索結果 → LLM への引き渡しの一連のパイプラインを実装。
- **frontend/**: Next.js + TailwindCSS によるサポート担当者向け UI。
- **docker-compose.yml**: backend / frontend / ベクトルストアなどをまとめて
  起動するローカル開発用構成。
- **sample_data/**: サポート FAQ 等のインデックス投入用サンプルデータ。
- **docs/**: 設計・運用に関するドキュメント。
- **CI ワークフロー** (`.github/workflows/`):
  - Python (backend) の lint / test
  - Node.js (frontend) の lint / test / build
  - `pip-audit` による依存パッケージの脆弱性検査
- **Dependabot** による依存パッケージ (pip / npm / GitHub Actions / Docker) の
  自動更新。
- リポジトリ運用ドキュメント: `README.md` / `CODE_OF_CONDUCT.md`。
- 開発補助ファイル: `.gitignore` / `.tool-versions`。

[Unreleased]: https://github.com/mohadayo/rag-support-assist/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mohadayo/rag-support-assist/releases/tag/v0.1.0
