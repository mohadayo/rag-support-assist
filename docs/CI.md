# CI ワークフロー（CI）

このドキュメントは `.github/workflows/` 配下のワークフロー 4 本を **横断的に** まとめた一次リファレンスです。backend (Python / FastAPI) と frontend (Next.js / TypeScript) で CI 構成が非対称なため、ジョブ単位の役割と前提をここに集約します。

CI 失敗の切り分け時、新規ワークフロー追加時、backend / frontend どちらが PR で走るかを確認したい時にまずここを参照してください。

## ワークフロー一覧

| ワークフロー | ファイル | 対象 | 目的 | 主なトリガー |
|---|---|---|---|---|
| `CI` | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | backend | `lint`（ruff）/ `test`（pytest + coverage）/ `security`（bandit + pip-audit） | `push` / `pull_request` to `main` |
| `frontend-ci` | [`.github/workflows/frontend-ci.yml`](../.github/workflows/frontend-ci.yml) | frontend | `typecheck + build`（tsc --noEmit → next build） | `frontend/**` の変更時のみ |
| `CodeQL` | [`.github/workflows/codeql.yml`](../.github/workflows/codeql.yml) | 両方 | Python / JavaScript / TypeScript の脆弱性静的解析（SAST） | `push` / `pull_request` to `main` + 週次 |
| `CI Auto Fix` | [`.github/workflows/ci-auto-fix.yml`](../.github/workflows/ci-auto-fix.yml) | 両方（自動化パイプライン） | CI の自動修正ジョブ（lock drift などの機械的修正） | 本リポジトリ運用上の自動フロー |

## `ci.yml`（backend）のジョブ構成

### `lint` ジョブ

- Python 3.11、`cache: pip`、`cache-dependency-path: backend/requirements-test.txt`
- `ruff==0.16.3` をインストールして `ruff check app/ tests/` を実行
- ruff バージョンを **ピン止め** することで、ローカルと CI の lint 結果を揃える

### `test` ジョブ

- Python 3.11、`cache: pip`、`backend/requirements.txt` と `backend/requirements-test.txt` の両方をキャッシュキーに
- `pip install -r requirements.txt -r requirements-test.txt`
- `pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=xml`
- `coverage.xml` を artifact として `actions/upload-artifact@v4` でアップロード（カバレッジを後続のレポートに繋ぐ想定）

### `security` ジョブ

backend 専用のセキュリティスキャン：

- `bandit==1.8.3`: Python の静的セキュリティスキャン。`bandit -r app/ -ll -ii --exit-zero` で、low severity / low confidence 以上を対象にスキャンし、exit code は 0 固定（警告だけ）
- `pip-audit==2.8.0`: 依存の既知脆弱性スキャン。`pip-audit --requirement requirements.txt --desc` で requirements.txt を直接走査

**非ブロッキング**: 両ツールとも現状は失敗で CI を止めず、ログで警告を出すだけ。将来 ブロッキングに切り替える場合は `--exit-zero` を外す / `pip-audit` の非ゼロ exit を受け入れる設定変更が必要。

## `frontend-ci.yml`（frontend）

backend とは **非対称** な設計：

- **`paths` フィルタ**: `frontend/**` と `.github/workflows/frontend-ci.yml` の変更時のみ走る。backend のみの PR では走らず、ランナー枠を無駄にしない
- **Node 版は `node-version-file: frontend/.node-version`** で参照（ワークフロー YAML に直書きしない）
- **ジョブは `typecheck-build` 1 本**: `npm ci` → `npx tsc --noEmit` → `npm run build`
- `tsc --noEmit` と `next build` は冗長に見えるが、`tsc --noEmit` は tests など build 対象外のファイルも型検査するため両方必要
- `timeout-minutes: 10`、`permissions: contents: read`、`concurrency.cancel-in-progress: true`

## 共通方針

### 権限は最小化（least privilege）

`frontend-ci.yml` は `permissions: contents: read` のみ。`ci.yml` は現状 `permissions:` 宣言が無く、既定（write を含む広い権限）になっているため、将来的に `contents: read` を宣言するリファクタ候補です（別 Issue で扱う）。

### 同一 ref で古いジョブはキャンセル

`frontend-ci.yml` は `concurrency` を宣言済み。`ci.yml` は未宣言のため、連続 push 時に古いジョブが残る可能性がある（これも将来のリファクタ候補）。

### Timeout の明示

- `frontend-ci.yml`: `timeout-minutes: 10`
- `ci.yml`: 既定（360 分）のため、将来的に明示化すべき

## ローカルで CI を再現する

### backend

```sh
cd backend
pip install -r requirements.txt -r requirements-test.txt
pip install ruff==0.16.3 bandit==1.8.3 pip-audit==2.8.0

ruff check app/ tests/                                      # lint ジョブ相当
pytest tests/ -v --cov=app --cov-report=term-missing        # test ジョブ相当
bandit -r app/ -ll -ii --exit-zero                          # security ジョブ (bandit)
pip-audit --requirement requirements.txt --desc             # security ジョブ (pip-audit)
```

### frontend

```sh
cd frontend
npm ci
npx tsc --noEmit     # typecheck
npm run build        # production build
```

## 新規ワークフロー追加時のチェックリスト

- [ ] `permissions:` をトップレベルで宣言し、既定を `contents: read` に絞る
- [ ] 書き込みが必要な場合は job 単位で `permissions:` を追加する
- [ ] `concurrency.group` と `cancel-in-progress: true` を宣言する
- [ ] `timeout-minutes` を各ジョブに明示する
- [ ] 対象レイヤーが限定される場合は `paths` フィルタで無駄なランナー起動を抑止する
- [ ] `uses:` の Action はメジャーバージョンのタグ（`@v4` 等）を指定し、Dependabot で追従する
- [ ] 可能なら `cache:` オプションを使って依存解決を再利用する
- [ ] 対応するローカル実行コマンドを `README.md` または本 `CI.md` に追記する

## 関連ドキュメント

- [`./ARCHITECTURE.md`](./ARCHITECTURE.md) — backend / frontend の責務分担（CI の非対称構成の背景）
- [`./CONFIGURATION.md`](./CONFIGURATION.md) — 環境変数と設定の全体像
- [`./EVAL.md`](./EVAL.md) — 回答品質の評価パイプライン（CI とは別軸の品質ゲート）
- [`./TROUBLESHOOTING.md`](./TROUBLESHOOTING.md) — CI 失敗を含む運用上の切り分け手順
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — ブランチ運用・コミット規則
- [`../.github/workflows/`](../.github/workflows) — 本ドキュメントが対象とするワークフロー YAML の一次定義
