# トラブルシューティング

`rag-support-assist` (backend: FastAPI + RAG / frontend: Next.js) の
ローカル開発でよく遭遇する問題と対処法をまとめています。

- セットアップ: [../README.md](../README.md)
- 設定項目: [CONFIGURATION.md](CONFIGURATION.md)
- 開発フロー: [../CONTRIBUTING.md](../CONTRIBUTING.md)

## 1. `docker compose up` が失敗する / DB に繋がらない

### 症状

- `postgres` コンテナが起動直後に exit する
- backend が `could not connect to server: Connection refused` を返す

### 対処

- ポート競合を確認 (`docker-compose.yml` の公開ポート):

  ```sh
  lsof -i :5432    # postgres
  lsof -i :8000    # backend (FastAPI)
  lsof -i :3000    # frontend (Next.js)
  ```

- 前回の残存コンテナ・ボリュームをクリアする:

  ```sh
  docker compose down -v
  docker compose up -d --build
  ```

- backend からは `.env` の `DATABASE_URL` を
  `postgresql://postgres:postgres@postgres:5432/rag` のように
  **コンテナ名** で指定する (ローカルの `localhost` ではなく)。

## 2. `pip install -r requirements.txt` で失敗する

### 症状

`psycopg2-binary` や `numpy` のビルドエラー。

### 対処

- Python バージョンが `.tool-versions` / `.python-version` (3.11) と
  合っているか確認 (`python --version`)。
- macOS で `psycopg2-binary` のビルドエラーが出る場合は libpq を導入:

  ```sh
  brew install libpq
  export LDFLAGS="-L$(brew --prefix libpq)/lib"
  export CPPFLAGS="-I$(brew --prefix libpq)/include"
  pip install --no-cache-dir -r requirements.txt
  ```

## 3. `pytest` がテスト DB で失敗する

### 対処

CI と同じコマンドをローカルで流してください:

```sh
cd backend
pip install -r requirements.txt
pip install -r requirements-test.txt
pytest tests/ -v --cov=app --cov-report=term-missing
```

DB を必要とするテストは `docker compose up postgres` で
postgres だけ起動してから流すか、テスト内部で SQLite などの
in-memory バックエンドを使うよう `.env.test` を分離してください。

## 4. `ruff check` がローカルで通っても CI で落ちる

### 原因

CI (`.github/workflows/ci.yml`) では `ruff==0.16.3` に固定されています。
ローカルの ruff が古い / 新しいと、検出ルールが異なることがあります。

### 対処

同じバージョンをローカルにも入れてください:

```sh
pip install ruff==0.16.3
ruff check app/ tests/
```

## 5. `pip-audit` / `bandit` に警告が出る

CI の `security` ジョブが `bandit -r app/ -ll -ii --exit-zero` と
`pip-audit --requirement requirements.txt --desc` を実行します。
`exit-zero` により CI 自体は落ちませんが、警告は放置せず対処する運用です。

- **bandit**: `# nosec` 抑制は根拠コメントを添えて必要最小限に。
- **pip-audit**: 該当パッケージを可能な範囲で更新するか、
  `--ignore-vuln <ID>` に理由を書き添える。

## 6. 文書アップロードが `413 Payload Too Large` を返す

### 原因

- 上限を超えるファイルサイズ
- あるいは chunker が単一の長文を分割できず 1 チャンクにまとめてしまい、
  上流 API のトークン上限に触れる (関連 Issue: #65)

### 対処

- `.env` の `MAX_UPLOAD_SIZE_MB` (`docs/CONFIGURATION.md` 参照) を
  必要に応じて調整する。
- ストリーミング読み込みへの改善は PR #78 で検討中。

## 7. フロントエンド (`frontend/`) が backend を呼べない

### 原因

CORS 設定または `NEXT_PUBLIC_API_URL` の設定ずれ。

### 対処

- `frontend/.env.local` の `NEXT_PUBLIC_API_URL` が backend の URL
  (デフォルト `http://localhost:8000`) を指しているか確認。
- backend の CORS 許可 origin に `http://localhost:3000` が
  含まれているか (`app/main.py` の `CORSMiddleware` 設定)。

## 8. CI が緑にならない

### チェックリスト

- `ruff check app/ tests/` が警告ゼロ
- `pytest tests/ -v --cov=app --cov-report=term-missing` が全通過
- 依存を追加した場合は `requirements.txt` / `requirements-test.txt` の
  両方に反映されているか
- Dependabot PR が積んでいる場合は先にマージして base を最新化してから
  自分の PR を rebase する

CI 定義は
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) にあります。

## 関連ドキュメント

- [../README.md](../README.md) — セットアップ手順
- [CONFIGURATION.md](CONFIGURATION.md) — 環境変数 / 設定項目一覧
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — 開発フロー
- [../CHANGELOG.md](../CHANGELOG.md) — 変更履歴
