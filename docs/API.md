# API リファレンス

RAG Support Assist バックエンド (`backend/app`) が提供する HTTP API の詳細仕様。README の「API 設計」節の詳細版で、フロントエンド実装・外部連携・障害調査の一次情報を意図しています。

- ベースパス: すべてのエンドポイントは `/api` プレフィックス配下
- リクエスト・レスポンスの Content-Type: 特記なき場合 `application/json`
- CORS 許可オリジン: 環境変数 `CORS_ORIGINS` に依存（デフォルト `http://localhost:3000`。カンマ区切りで複数指定可）
- 共通レスポンスヘッダ（`SecurityHeadersMiddleware` により全応答に付与）:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`

FastAPI 由来の自動生成ドキュメントも起動後に参照可能:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## エンドポイント一覧

| メソッド | パス | 概要 |
|---------|------|------|
| POST | `/api/query` | 問い合わせ文を受け取り、RAG で回答候補を生成 |
| POST | `/api/documents/upload` | 文書ファイルをアップロードしてベクトル DB に登録 |
| GET | `/api/documents` | 登録済み文書の一覧を取得 |
| DELETE | `/api/documents/{doc_id}` | 文書を削除 |
| GET | `/api/health` | ヘルスチェック（DB 接続確認付き） |

---

## POST /api/query

問い合わせ文を受け取り、ベクトル検索 → LLM による RAG で回答候補を生成します。

### リクエスト

- Content-Type: `application/json`

| フィールド | 型 | 必須 | デフォルト | 制約 |
|-----------|-----|------|-----------|------|
| `query` | string | yes | – | 1〜5000 文字。空白のみ不可（前後の空白は自動 trim） |
| `tone` | string | no | `"standard"` | `"polite"` \| `"standard"` \| `"concise"` のいずれか |

`tone` の意味:

| 値 | 意図 |
|----|------|
| `polite` | 丁寧調（例: 「〜でございます」） |
| `standard` | 標準の敬体（デフォルト） |
| `concise` | 要点のみ簡潔に |

### レスポンス (200 OK)

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `answer` | string | 生成された回答本文 |
| `sources` | `SourceDocument[]` | 参照した根拠チャンクの配列 |
| `should_escalate` | boolean | エスカレーション推奨か |
| `escalation_reason` | string \| null | エスカレーション推奨時の理由。それ以外は `null` |

`SourceDocument`:

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `content` | string | 参照したチャンク本文 |
| `document_name` | string | 元文書名（アップロード時のファイル名） |
| `category` | string | `faq` \| `terms` \| `manual` \| `history` |
| `relevance_score` | number | 関連度（0.0〜1.0、小数第 3 位で丸め）。コサイン距離を `max(0.0, 1.0 - distance)` で正規化した値 |

### エラー

| ステータス | 発生条件 |
|-----------|---------|
| 422 | `query` が空、5000 文字超過、または `tone` が enum 外（Pydantic バリデーション） |
| 500 | 回答生成中に予期しない例外が発生 |
| 503 | ベクトル DB 接続失敗、または OpenAI API エラー |

### 例

リクエスト:

```bash
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"注文した商品が届きません。注文番号はA2345です。","tone":"polite"}'
```

レスポンス:

```json
{
  "answer": "お問い合わせありがとうございます。注文番号A2345の配送状況を確認いたします……",
  "sources": [
    {
      "content": "発送後の配送状況は追跡番号よりご確認いただけます……",
      "document_name": "faq.txt",
      "category": "faq",
      "relevance_score": 0.812
    }
  ],
  "should_escalate": false,
  "escalation_reason": null
}
```

---

## POST /api/documents/upload

文書ファイルをアップロードし、チャンク化してベクトル DB に登録します。

### リクエスト

- Content-Type: `multipart/form-data`

| フィールド | 型 | 必須 | デフォルト | 制約 |
|-----------|-----|------|-----------|------|
| `file` | file | yes | – | 拡張子 `.txt` \| `.md` \| `.csv`（大文字小文字問わず）。UTF-8。サイズ上限は環境変数 `MAX_UPLOAD_SIZE_MB`（デフォルト 10MB） |
| `category` | string | no | `"faq"` | `faq` \| `terms` \| `manual` \| `history` |

アップロードはストリーミング読み込みで実装されており、`MAX_UPLOAD_SIZE_MB` を超過した瞬間に残りを読まずに 413 を返します。

### レスポンス (200 OK)

`DocumentInfo`:

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `id` | string | 生成された文書 ID（UUIDv4） |
| `name` | string | アップロード時のファイル名 |
| `category` | string | 指定したカテゴリ |
| `chunk_count` | number | 生成されたチャンク数 |
| `uploaded_at` | string | ISO 8601（UTC）のタイムスタンプ |

### エラー

| ステータス | 発生条件 |
|-----------|---------|
| 400 | ファイル名なし / 拡張子非対応 / カテゴリ非対応 / ファイルが空 |
| 413 | ファイルサイズが `MAX_UPLOAD_SIZE_MB` 上限超過 |
| 422 | `file` が multipart フィールドとして欠落（FastAPI 側で 422） |

### 例

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F 'file=@sample_data/faq.txt' \
  -F 'category=faq'
```

```json
{
  "id": "8f14e45f-ceea-467a-a4f8-1b3e9e2d5a01",
  "name": "faq.txt",
  "category": "faq",
  "chunk_count": 23,
  "uploaded_at": "2026-09-09T10:15:30.123456+00:00"
}
```

---

## GET /api/documents

登録済み文書の一覧を返します。

### リクエスト

パラメータなし。

### レスポンス (200 OK)

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `documents` | `DocumentInfo[]` | 登録文書の配列 |
| `total` | number | 登録文書数 |

### 例

```bash
curl http://localhost:8000/api/documents
```

```json
{
  "documents": [
    {
      "id": "8f14e45f-ceea-467a-a4f8-1b3e9e2d5a01",
      "name": "faq.txt",
      "category": "faq",
      "chunk_count": 23,
      "uploaded_at": "2026-09-09T10:15:30.123456+00:00"
    }
  ],
  "total": 1
}
```

---

## DELETE /api/documents/{doc_id}

指定 ID の文書に紐づくすべてのチャンクをベクトル DB から削除します。

### パスパラメータ

| 名前 | 型 | 説明 |
|------|-----|------|
| `doc_id` | string | 対象文書の ID（アップロード時に発行された UUID） |

### レスポンス (200 OK)

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `deleted_chunks` | number | 削除されたチャンク数 |
| `document_id` | string | 対象文書 ID |

### エラー

| ステータス | 発生条件 |
|-----------|---------|
| 404 | 指定 ID の文書が見つからない（削除件数 0） |

### 例

```bash
curl -X DELETE http://localhost:8000/api/documents/8f14e45f-ceea-467a-a4f8-1b3e9e2d5a01
```

```json
{
  "deleted_chunks": 23,
  "document_id": "8f14e45f-ceea-467a-a4f8-1b3e9e2d5a01"
}
```

---

## GET /api/health

DB 接続の疎通確認を含むヘルスチェック。ロードバランサや監視ツールが状態をステータスコードで判定できるよう、接続失敗時は 503 を返します。

### レスポンス (200 OK)

```json
{
  "status": "ok",
  "vector_db": "connected",
  "document_chunks": 42
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `status` | string | 固定値 `"ok"` |
| `vector_db` | string | 固定値 `"connected"` |
| `document_chunks` | number | 登録チャンク総数 |

### レスポンス (503 Service Unavailable)

```json
{
  "status": "degraded",
  "vector_db": "disconnected"
}
```

DB 接続で例外が発生した場合に返却されます。監視・LB からはステータスコードのみで判定可能です。

---

## エラーレスポンス共通フォーマット

FastAPI 由来のエラーは以下の形式で返されます。

`HTTPException` (4xx / 5xx):

```json
{ "detail": "エラーメッセージ" }
```

Pydantic バリデーションエラー (422):

```json
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "問い合わせ文を入力してください",
      "type": "value_error"
    }
  ]
}
```

---

## 関連ドキュメント

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — システム構成・データフロー
- [`docs/CONFIGURATION.md`](CONFIGURATION.md) — 環境変数（`CORS_ORIGINS`, `MAX_UPLOAD_SIZE_MB` など）の一覧
- [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 503 / 500 が返る際の切り分け手順
