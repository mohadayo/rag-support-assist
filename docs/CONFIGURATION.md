# 環境変数リファレンス

RAG Support Assist のバックエンドが参照するすべての環境変数を一覧化したものです。
新しい環境変数を追加する際は、必ず本ドキュメントと `backend/.env.example` の両方を更新してください。

## 必須

| 変数名 | 用途 | 参照箇所 |
|--------|------|----------|
| `OPENAI_API_KEY` | OpenAI Embedding / Chat Completion API 呼び出し時の認証に使用します。未設定の場合、OpenAI クライアントの初期化時にエラーとなります。 | `backend/app/services/embeddings.py`, `backend/app/services/rag.py` |
| `DATABASE_URL` | PostgreSQL (pgvector) への接続 URL です。未設定の場合、アプリ起動時 (マイグレーション) やクエリ実行時に `RuntimeError` を送出します。 | `backend/app/services/vectorstore.py` |

### 例

```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
DATABASE_URL=postgres://user:password@localhost:5432/rag_support?sslmode=disable
```

## 任意 (デフォルト値あり)

| 変数名 | デフォルト | 型 / 制約 | 用途 | 参照箇所 |
|--------|-----------|----------|------|----------|
| `CORS_ORIGINS` | `http://localhost:3000` | カンマ区切り文字列 | FastAPI の CORS ミドルウェアで許可するオリジン。カンマ区切りで複数指定できます。 | `backend/app/main.py` |
| `RAG_MODEL` | `gpt-4o-mini` | OpenAI Chat モデル名 | 回答生成 (`generate_answer`) とエスカレーション判定 (`_check_escalation`) の双方で共通利用します。 | `backend/app/services/rag.py` |
| `MAX_UPLOAD_SIZE_MB` | `10` | 正の整数 (MB) | 文書アップロード API で許容するファイルサイズ上限。不正値 (負・0・非数値) 指定時はデフォルト値にフォールバックし警告ログを出力します。 | `backend/app/routers/documents.py` |

### 挙動の詳細

- **`CORS_ORIGINS`**
  例: `CORS_ORIGINS=http://localhost:3000,https://example.com`
  値は各要素で `strip()` されるためカンマ前後の空白は許容されます。
- **`RAG_MODEL`**
  `gpt-4o-mini` を含む OpenAI Chat モデル名を指定します。エスカレーション判定は `response_format={"type": "json_object"}` を利用するため、JSON モードをサポートするモデルを指定してください。
- **`MAX_UPLOAD_SIZE_MB`**
  アプリ起動時に一度だけ解決され、実行中に環境変数を変更しても反映されません。変更する場合はプロセスを再起動してください。

## デプロイ環境ごとの設定例

### ローカル開発 (Docker Compose)

`backend/.env` を編集します (`backend/.env.example` をコピーして使用してください)。

```bash
cd backend
cp .env.example .env
# .env を編集
```

### Fly.io

`fly secrets set` で機密情報を、`fly.toml` の `[env]` セクションで非機密設定を管理することを推奨します。

```bash
fly secrets set OPENAI_API_KEY=sk-xxxx DATABASE_URL="postgres://..."
fly secrets set RAG_MODEL=gpt-4o-mini
```

## 環境変数を追加する際のチェックリスト

新しい環境変数を導入する場合は、以下すべてを更新してください。

- [ ] コード側で `os.getenv()` などで参照する
- [ ] `backend/.env.example` に追記 (デフォルト値と用途をコメント)
- [ ] 本ドキュメント (`docs/CONFIGURATION.md`) に追記
- [ ] 変更内容を PR 説明に記載
