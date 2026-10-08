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
| `RAG_TEMPERATURE` | `0.3` | 浮動小数 (閉区間 `0.0〜2.0`、範囲外・非数値はデフォルトへフォールバック) | 回答生成 (`generate_answer`) の `temperature`。エスカレーション判定 (`_check_escalation`) は決定的な判定を得るため常に `0` 固定で、本変数の影響を受けません。 | `backend/app/services/rag.py` |
| `RAG_MAX_TOKENS` | `1500` | 整数 (1 以上、0 以下・非数値はデフォルトへフォールバック) | 回答生成 (`generate_answer`) の `max_tokens`。エスカレーション判定 (`_check_escalation`) は常に `200` 固定で、本変数の影響を受けません。 | `backend/app/services/rag.py` |
| `MAX_UPLOAD_SIZE_MB` | `10` | 正の整数 (MB) | 文書アップロード API で許容するファイルサイズ上限。不正値 (負・0・非数値) 指定時はデフォルト値にフォールバックし警告ログを出力します。 | `backend/app/routers/documents.py` |
| `CHUNK_SIZE` | `500` | 整数 (最小 50 にクランプ、非数値時はデフォルトへフォールバック) | チャンク化 (`chunk_text`) の 1 chunk あたりの最大文字数。Embedding API のトークン消費量と検索の粒度に直結するチューニングパラメータ。 | `backend/app/services/chunker.py` |
| `CHUNK_OVERLAP` | `100` | 0 以上の整数 (`CHUNK_SIZE` 以上を指定した場合は `CHUNK_SIZE // 2` にクランプ) | 隣接 chunk 間で末尾を次 chunk 冒頭に持ち込む文字数。境界コンテキストを保持して検索精度を高めるための設定。 | `backend/app/services/chunker.py` |

### 挙動の詳細

- **`CORS_ORIGINS`**
  例: `CORS_ORIGINS=http://localhost:3000,https://example.com`
  値は各要素で `strip()` されるためカンマ前後の空白は許容されます。
- **`RAG_MODEL`**
  `gpt-4o-mini` を含む OpenAI Chat モデル名を指定します。エスカレーション判定は `response_format={"type": "json_object"}` を利用するため、JSON モードをサポートするモデルを指定してください。
- **`RAG_TEMPERATURE`**
  回答生成時の `temperature` を指定します。閉区間 `0.0〜2.0` の範囲で、範囲外・非数値 (空文字列を含む) を指定した場合はデフォルト値 (`0.3`) にフォールバックします。値を小さくすると出力は決定的になり再現性が高くなり、大きくすると表現の多様性が増えますが参照文書から外れたハルシネーションのリスクも高まります。なお、エスカレーション判定 (`_check_escalation`) は決定性を担保するため常に `0` 固定で、本変数の影響を受けません。
- **`RAG_MAX_TOKENS`**
  回答生成時の `max_tokens` を指定します。1 以上の整数で、0 以下・非数値 (空文字列を含む) を指定した場合はデフォルト値 (`1500`) にフォールバックします。OpenAI API 側では 0 や負値がエラーになるため、明示的にデフォルトへ寄せています。値を増やすと長文の回答を生成しやすくなりますが、1 リクエストあたりのコストと応答時間も増加します。なお、エスカレーション判定 (`_check_escalation`) は JSON の短い出力のみを扱うため `200` 固定で、本変数の影響を受けません。
- **`MAX_UPLOAD_SIZE_MB`**
  アプリ起動時に一度だけ解決され、実行中に環境変数を変更しても反映されません。変更する場合はプロセスを再起動してください。
- **`CHUNK_SIZE`**
  1 chunk の最大文字数を指定します。値を大きくすると 1 リクエストあたりの参照文脈量は増えますが Embedding / Chat の 1 リクエストあたりコストが上がり、逆に小さくすると検索粒度は細かくなる代わりに文脈が分断されやすくなります。50 未満・非数値を指定した場合はそれぞれ 50 / デフォルト値 (`500`) にフォールバックします。
- **`CHUNK_OVERLAP`**
  chunk 境界での文脈欠落を防ぐため、末尾 N 文字を次 chunk の冒頭にコピーします。`CHUNK_SIZE` 以上の値を指定すると個々の chunk が `CHUNK_SIZE` を無制限に超過してしまうため、自動的に `CHUNK_SIZE // 2` にクランプされます (`chunker.py` 側の安全策)。0 を指定するとオーバーラップは無効化されます。

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
