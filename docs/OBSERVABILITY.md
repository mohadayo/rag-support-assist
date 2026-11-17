# 観測性 (Observability)

`rag-support-assist` backend (FastAPI) が本番・ステージング・ローカルで出力する
アクセスログ、全応答に付与するセキュリティヘッダ、ヘルスチェックエンドポイントの
仕様をまとめ、監視・ロードバランサ設定・障害切り分けの基礎リファレンスとします。

- 実装: [`../backend/app/main.py`](../backend/app/main.py)
- 設定項目全般: [`CONFIGURATION.md`](CONFIGURATION.md)
- CI 構成: [`CI.md`](CI.md)
- 症状別切り分け: [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)

## 1. アクセスログ

### フォーマット

`logging.basicConfig` の `format` で以下を固定しています。

```
%(asctime)s %(levelname)s %(name)s: %(message)s
```

アクセスログ本体は `RequestLoggingMiddleware` が以下の `message` を出力します。

```
<METHOD> <PATH> <STATUS> <DURATION_ms>ms
```

実際の出力例:

```
2026-11-17 12:34:56,789 INFO backend.app.main: POST /api/query 200 128.3ms
2026-11-17 12:34:57,012 INFO backend.app.main: GET /api/health 200 4.1ms
2026-11-17 12:34:58,345 INFO backend.app.main: GET /api/health 503 2.0ms
```

### フィールド説明

| フィールド | 意味 | 備考 |
| --- | --- | --- |
| `%(asctime)s` | ローカルタイム | タイムゾーンはコンテナ `TZ` 環境変数に従う |
| `%(levelname)s` | ログレベル | 通常は `INFO`、例外発生時は `ERROR` が別途出力される |
| `%(name)s` | ロガー名 | `backend.app.main` ほか、各モジュール名 |
| `METHOD` | HTTP メソッド | `GET` / `POST` / `DELETE` など |
| `PATH` | リクエストパス | クエリ文字列は含まない |
| `STATUS` | HTTP ステータスコード | 3 桁の整数 |
| `DURATION_ms` | 応答までの処理時間 (ms) | `time.time()` ベースの壁時計、小数第 1 位まで |

### 代表的な抽出コマンド

```sh
# 5xx のみ抽出
docker compose logs backend | grep -E ' 5[0-9]{2} '

# /api/query の平均応答時間を概算
docker compose logs backend \
  | awk '/POST \/api\/query/ { gsub("ms","",$NF); sum+=$NF; n++ } END { if (n) print sum/n " ms (n=" n ")" }'

# 遅い (500ms 以上) リクエストのみ抽出
docker compose logs backend | awk '/ms$/ && $NF+0 >= 500'
```

### 変更時の注意

- `RequestLoggingMiddleware` は `BaseHTTPMiddleware` ベースのため、`call_next`
  内で発生した未捕捉例外は上位の `ExceptionMiddleware` に委譲され、
  ここでのログは出ません。例外ログは FastAPI / Starlette 既定のスタックトレース
  出力に依存します。
- フォーマットを変更する場合は上記 `grep` / `awk` パターンを使っている
  監視基盤・ランブックへの波及を必ず確認してください。

## 2. セキュリティヘッダ

`SecurityHeadersMiddleware` が全応答に以下を付与します。

| ヘッダ | 値 | 目的 |
| --- | --- | --- |
| `X-Content-Type-Options` | `nosniff` | JSON を別 MIME として解釈させる MIME sniffing 攻撃を抑止 |
| `X-Frame-Options` | `DENY` | API を `<iframe>` に埋め込ませない (clickjacking 対策) |
| `Referrer-Policy` | `no-referrer` | 内部 URL / クエリ文字列が外部リンク先 Referrer に漏れることを抑止 |

### 上書き挙動

ミドルウェアは既にレスポンスに同名ヘッダが設定されている場合、**上書きしません**
(実装上は `if key not in response.headers` で判定)。これは以下を想定しています。

- 個別ルートで `X-Frame-Options: SAMEORIGIN` を返したい場合
- テストでヘッダ付与挙動を検証する際にフィクスチャ側で明示的に値を差し込む場合

### 追加・変更時の手順

1. `backend/app/main.py` の `_SECURITY_HEADERS` 辞書に追記
2. `backend/tests/test_security_headers.py` に期待値を追加
3. ブラウザから直接叩かれない API のため CSP 相当の重い設定は原則不要。
   追加する場合は `TROUBLESHOOTING.md` に影響範囲を記載する

### 検証コマンド

```sh
curl -I http://localhost:8000/api/health
# -> X-Content-Type-Options: nosniff
#    X-Frame-Options: DENY
#    Referrer-Policy: no-referrer
```

## 3. ヘルスチェック: `/api/health`

### 仕様

- メソッド: `GET`
- 認証: 不要
- 動作: `get_chunk_count()` を呼び出し DB 接続性を確認

### レスポンス

正常時 (HTTP 200):

```json
{
  "status": "ok",
  "vector_db": "connected",
  "document_chunks": 1234
}
```

DB 接続異常時 (HTTP 503):

```json
{
  "status": "degraded",
  "vector_db": "disconnected"
}
```

例外内容は `logger.exception` によりスタックトレース付きでログ出力されます。

### 推奨プローブ設定

ロードバランサ / Kubernetes 等で利用する場合の目安です。

| 項目 | 推奨値 | 根拠 |
| --- | --- | --- |
| パス | `/api/health` | 認証不要・副作用なし |
| タイムアウト | 2 秒 | `get_chunk_count` は単純な `COUNT` クエリのため |
| 失敗閾値 | 連続 3 回 | 一時的な DB 接続揺らぎで excessive restart しないため |
| 成功閾値 | 1 回 | 復旧判定を遅らせない |
| 間隔 | 10 秒 | トラフィック量に応じて調整 |

### Kubernetes manifest 例

```yaml
livenessProbe:
  httpGet:
    path: /api/health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /api/health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

liveness と readiness で現状同じエンドポイントを使っています。
DB 断で 503 が継続する場合、readiness により新規トラフィックが止まり、
liveness により最終的に Pod 再作成されます。DB 側の復旧を優先したい場合は
`livenessProbe` の `failureThreshold` を大きめ (例: 10) にしてください。

## 4. 関連ドキュメント

- [`../README.md`](../README.md) — プロジェクト概要とクイックスタート
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — システム全体像とデータフロー
- [`CONFIGURATION.md`](CONFIGURATION.md) — ログレベルや CORS 等の環境変数
- [`CI.md`](CI.md) — `bandit` / `pip-audit` などセキュリティ関連 CI の仕組み
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 障害発生時の切り分け手順
- [`../SECURITY.md`](../SECURITY.md) — 脆弱性報告経路・サポート対象バージョン
