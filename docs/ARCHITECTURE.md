# アーキテクチャ設計

`rag-support-assist` (カスタマーサポート回答支援 RAG) のシステム全体像・主要コンポーネント・データフロー・拡張ポイントを俯瞰する。

- 設定パラメータの詳細は `docs/CONFIGURATION.md`
- 個別の障害調査は `docs/TROUBLESHOOTING.md`

本書は "全体を短時間で把握する" ためのマップとし、実装詳細は各モジュールと関連ドキュメントに委ねる。

## 目次

- [1. 全体構成](#1-全体構成)
- [2. 主要コンポーネント](#2-主要コンポーネント)
- [3. データフロー](#3-データフロー)
- [4. API 表面](#4-api-表面)
- [5. 拡張ポイント](#5-拡張ポイント)
- [6. 非機能要件](#6-非機能要件)

## 1. 全体構成

```
+--------------+   HTTP    +---------------------------+   埋め込みAPI    +------------+
|  frontend    | --------> |  backend (FastAPI)        | ---------------> |  LLM / 埋め込み |
| (Web UI)     |           |  app/main.py              |                  | プロバイダ  |
+--------------+           |  app/routers/{documents,  |                  +------------+
                           |               query}.py   |
                           |  app/services/{chunker,   |
                           |   embeddings, vectorstore,|
                           |   rag}.py                 |
                           +--------------+------------+
                                          |
                                          | ベクトル永続化
                                          v
                                 +----------------+
                                 |  Vector Store  |
                                 |  (docker-compose|
                                 |  で提供)        |
                                 +----------------+

サンプルデータ: sample_data/
```

`docker-compose.yml` で backend とベクトルストアが束ねられている。frontend は独立に開発サーバーが起動する構成。

## 2. 主要コンポーネント

### 2.1 API 層 (`backend/app`)

| モジュール | 責務 |
| :-- | :-- |
| `main.py` | FastAPI アプリケーションのブートストラップ・ミドルウェア・ルータ登録 |
| `models.py` | Pydantic モデル (リクエスト・レスポンスの契約) |
| `routers/documents.py` | 文書の取り込み・削除 API |
| `routers/query.py` | 質問応答 API (RAG 実行の入口) |

### 2.2 RAG コアサービス (`backend/app/services`)

| モジュール | 責務 |
| :-- | :-- |
| `chunker.py` | 文書を意味的にまとまった単位に分割する。区切り文字・最大長を設定で制御 |
| `embeddings.py` | チャンクをベクトル表現に変換する。埋め込みプロバイダとの疎結合を保つ |
| `vectorstore.py` | ベクトルの永続化・類似検索。バックエンドを差し替え可能にする抽象を意識 |
| `rag.py` | 検索 + LLM 生成のオーケストレーション。ルーターから呼ばれる |

各サービスは "純粋な関数 / クラス" として書かれ、FastAPI 依存を持たない。ユニットテストしやすさを優先している。

### 2.3 データ

- `sample_data/`: 初期投入用のサンプル文書
- ベクトルストア: `docker-compose` の外部サービスとして提供され、backend からは接続情報 (`.env`) 経由でアクセスする

## 3. データフロー

### 3.1 取り込みパイプライン (Ingest)

```
文書 (テキスト/ファイル)
   |
   v
POST /documents (routers/documents.py)
   |
   v
chunker.split(text)  --> チャンクの列
   |
   v
embeddings.embed(chunks) --> 各チャンクのベクトル
   |
   v
vectorstore.upsert(vectors, metadata) --> 永続化
```

### 3.2 質問応答パイプライン (Query)

```
質問 (ユーザー)
   |
   v
POST /query (routers/query.py)
   |
   v
embeddings.embed(question) --> クエリベクトル
   |
   v
vectorstore.similarity_search(vector, k) --> 上位 k チャンク
   |
   v
rag.generate(question, chunks) --> LLM で回答生成
   |
   v
JSON レスポンス (回答 + 出典)
```

## 4. API 表面

代表的なエンドポイント:

| メソッド | パス | 責務 |
| :-- | :-- | :-- |
| `POST` | `/documents` | 文書の取り込み (チャンク → 埋め込み → 保存) |
| `DELETE` | `/documents/{id}` | 文書の削除 (関連ベクトルも掃除) |
| `POST` | `/query` | 質問を投げ、根拠付きの回答を得る |

正確な入出力スキーマは OpenAPI (FastAPI が自動生成) と `app/models.py` を参照する。

## 5. 拡張ポイント

### 5.1 ベクトルストアの差し替え

`services/vectorstore.py` の実装を差し替えれば、上位 (`rag.py` / ルータ) は影響を受けない。追加時は下記を守る。

- 抽象インターフェイス (upsert / similarity_search / delete) を維持する
- 接続情報は `.env` に集約する
- テストで in-memory 実装を差し込めるようにする

### 5.2 LLM / 埋め込みプロバイダの差し替え

`services/embeddings.py` と `services/rag.py` の LLM 呼び出し部を差し替える。プロバイダ毎の API キーは `.env` に集約する。

### 5.3 チャンク戦略の変更

`services/chunker.py` を差し替える。区切り文字・最大長・オーバーラップは設定値として外出しする方針を守る。

## 6. 非機能要件

### 観測

- 構造化ログ (JSON 1 行) を推奨
- 主要メトリクス: 取り込み件数 / クエリ数 / 平均検索時間 / LLM 呼び出しレイテンシ
- 具体は `docs/CONFIGURATION.md` の該当項目に従う

### セキュリティ

- API キー・接続情報はソースにハードコードしない (`.env` に集約)
- CI では bandit と pip-audit を実行し、既知脆弱性を継続監視
- SECURITY.md の報告経路を尊重する

### テスト

- `backend/tests/` にユニットテストを配置
- 埋め込み・LLM 呼び出しはモック化してオフラインで実行できる状態を保つ
- CI で ruff (lint) + pytest (カバレッジ) + bandit + pip-audit を実行

## 変更履歴

- 2026-08: 初版作成。
