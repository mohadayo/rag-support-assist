# コントリビュートガイド

RAG Support Assist へのコントリビュートを検討いただきありがとうございます。
このドキュメントは、本リポジトリに Issue を起票したり Pull Request を送ったりする際の共通ルールをまとめたものです。

初めての方は本ページを一読してから作業を始めてください。

## 目次

1. [はじめに](#1-はじめに)
2. [行動規範](#2-行動規範)
3. [開発環境セットアップ](#3-開発環境セットアップ)
4. [ブランチ運用](#4-ブランチ運用)
5. [コミットメッセージ規約](#5-コミットメッセージ規約)
6. [ローカルで実行するチェック](#6-ローカルで実行するチェック)
7. [Pull Request の出し方](#7-pull-request-の出し方)
8. [Issue の起票](#8-issue-の起票)
9. [セキュリティ脆弱性の報告](#9-セキュリティ脆弱性の報告)
10. [変更履歴 (CHANGELOG) の更新](#10-変更履歴-changelog-の更新)

---

## 1. はじめに

このガイドは以下のような方を対象にしています。

- 本リポジトリに機能追加・バグ修正・ドキュメント改善の Pull Request を送りたい方
- 動作不具合・改善要望を Issue として登録したい方
- ローカル環境で backend / frontend を動かして挙動を確認したい方

本リポジトリは **カスタマーサポート回答支援 AI (RAG)** の実装であり、以下 2 コンポーネントで構成されます。

- `backend/`  : Python 3.11 + FastAPI + PostgreSQL(pgvector) + OpenAI API
- `frontend/` : Next.js 15 + React 19 + Tailwind CSS 4

アーキテクチャや API 仕様の全体像は [`README.md`](./README.md) を参照してください。

## 2. 行動規範

本プロジェクトに参加するすべての方は [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) を尊重してください。
Issue / PR / コメント / レビューを含むあらゆるやり取りが対象です。

## 3. 開発環境セットアップ

ローカルでの起動方法は [`README.md` の「ローカル起動方法」](./README.md#ローカル起動方法) にまとまっています。要点のみ再掲します。

### 前提ツール

| ツール | バージョン | 用途 |
|--------|-----------|------|
| Python | 3.11+ | backend 実行環境 |
| Node.js | 18+ | frontend 実行環境 |
| Docker / Docker Compose | 最新安定版 | PostgreSQL(pgvector) 起動 |
| OpenAI API キー | - | LLM / Embedding 呼び出し |

### 推奨: Docker Compose で一括起動

```bash
cp .env.example .env 2>/dev/null || true
# .env を編集して OPENAI_API_KEY を設定

docker compose up --build
```

- Frontend: <http://localhost:3000>
- Backend API: <http://localhost:8000>

環境変数の一覧・デフォルト値は [`docs/CONFIGURATION.md`](./docs/CONFIGURATION.md) を参照してください。

## 4. ブランチ運用

- **`main` ブランチへの直接コミットは禁止** です。すべての変更は Pull Request 経由で取り込みます。
- 作業ブランチは `main` から派生させてください。
- ブランチ名はスラッシュ区切りで、目的が伝わる短い英語にしてください。

| 種別 | プレフィックス | 例 |
|------|--------------|----|
| 機能追加 | `feat/` | `feat/streaming-answer` |
| バグ修正 | `fix/` | `fix/chunker-oversize-split` |
| ドキュメント | `docs/` | `docs/add-contributing-guide` |
| リファクタ | `refactor/` | `refactor/vectorstore-connection` |
| テスト追加 | `test/` | `test/documents-router` |
| 雑務 (CI / 依存更新など) | `chore/` | `chore/bump-fastapi` |

ブランチ名が既存と衝突する場合は末尾に日付 (`-YYYYMMDD`) を付けて回避してください。

## 5. コミットメッセージ規約

[Conventional Commits](https://www.conventionalcommits.org/ja/v1.0.0/) に準拠します。

```
<type>(<scope>): <subject>

<body>

<footer>
```

### type

| type | 用途 |
|------|------|
| `feat` | 新機能追加 |
| `fix` | バグ修正 |
| `docs` | ドキュメントのみの変更 |
| `style` | コードの意味に影響しないフォーマット変更 |
| `refactor` | 挙動を変えないコード整理 |
| `perf` | パフォーマンス改善 |
| `test` | テストの追加・修正 |
| `chore` | ビルド・依存関係・CI などの雑務 |
| `revert` | 変更の取り消し |

### 例

```
feat(query): tone パラメータに "concise" を追加
fix(chunker): chunk_size を超える単一文を強制分割する
docs: CONTRIBUTING.md を追加
chore(deps): fastapi を 0.122.0 → 0.140.13 に更新
```

本文 (body) と Footer (`Closes #<n>` など) は任意ですが、非自明な変更ではできる限り記載してください。

## 6. ローカルで実行するチェック

以下のコマンドは [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) が実行するものと **完全に一致** させています。PR を送る前にローカルでパスすることを確認してください。

### 6.1 Backend Lint (ruff)

```bash
cd backend
pip install ruff==0.16.3
ruff check app/ tests/
```

設定は [`backend/pyproject.toml`](./backend/pyproject.toml) の `[tool.ruff]` セクションを参照してください。現状は `select = ["F"]` (pyflakes 相当) のみ有効です。

### 6.2 Backend テスト (pytest)

```bash
cd backend
pip install -r requirements.txt -r requirements-test.txt
pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=xml
```

新規機能・バグ修正には可能な限りテストを追加してください。

### 6.3 Backend セキュリティ検査

```bash
cd backend
pip install bandit==1.8.3 pip-audit==2.8.0

# 静的解析 (中/高リスクのみ)
bandit -r app/ -ll -ii --exit-zero

# 依存脆弱性スキャン
pip-audit --requirement requirements.txt --desc
```

新規に **中/高リスクの警告** や **未対応の CVE** を追加しないよう注意してください。

### 6.4 Frontend

現状 `frontend/package.json` には `lint` スクリプトが定義されていません。代替として TypeScript 型検査を兼ねてビルドを走らせることを推奨します。

```bash
cd frontend
npm install
npm run build
```

`lint` スクリプト自体の導入は歓迎します。追加する場合は本ガイドと `PULL_REQUEST_TEMPLATE.md` のチェックリストも合わせて更新してください。

## 7. Pull Request の出し方

1. `main` の最新を取り込んだ作業ブランチで変更を行う。
2. [「6. ローカルで実行するチェック」](#6-ローカルで実行するチェック) がすべてパスすることを確認する。
3. GitHub 上で Pull Request を作成する。テンプレート [`.github/PULL_REQUEST_TEMPLATE.md`](./.github/PULL_REQUEST_TEMPLATE.md) が自動で読み込まれるので、以下を必ず埋めてください。
   - **変更概要**: 何を変えたか / なぜ必要か
   - **対応 Issue**: `Closes #<n>` または `Refs #<n>`
   - **影響範囲**: 該当するチェックボックスをオン
   - **動作確認手順**: レビュアーが再現できる粒度で
   - **チェックリスト**: 該当項目をすべてオン
4. PR は原則 **Draft ではなく Ready for Review** で作成してください。作業中のみ Draft を使い、レビュー準備が整ったら解除します。
5. マージ方式は **Squash and merge** を推奨します。

## 8. Issue の起票

`.github/ISSUE_TEMPLATE/` に以下 2 種類のテンプレートを用意しています。用途に合わせて選択してください。

| テンプレート | 用途 |
|-------------|------|
| [`bug_report.md`](./.github/ISSUE_TEMPLATE/bug_report.md) | バグ報告 (再現手順・期待値・実測値を記載) |
| [`feature_request.md`](./.github/ISSUE_TEMPLATE/feature_request.md) | 機能追加・改善提案 (背景・提案内容・代替案を記載) |

重複起票を避けるため、既存の Open Issue を検索してから作成してください。

## 9. セキュリティ脆弱性の報告

**セキュリティ脆弱性は公開 Issue に投稿しないでください。**

報告経路については、追加予定の `SECURITY.md` (see #71) を参照してください。同ファイルが公開されるまでの間は、リポジトリオーナー宛にプライベートな連絡手段 (GitHub Security Advisories 等) を用いてご連絡ください。

## 10. 変更履歴 (CHANGELOG) の更新

本リポジトリは [Keep a Changelog v1.1.0](https://keepachangelog.com/ja/1.1.0/) 形式で [`CHANGELOG.md`](./CHANGELOG.md) を管理しています。

利用者影響のある変更 (機能追加・仕様変更・バグ修正・セキュリティ修正など) を含む PR では、`[Unreleased]` セクション配下の適切な見出し (`Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`) に 1 行追記してください。

内部リファクタや CI 設定変更など、利用者に影響しない変更については更新不要です。

---

ご不明点があれば Issue でお気軽にご質問ください。よろしくお願いします！
