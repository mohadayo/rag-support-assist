# Security Policy

## 対応バージョン

`main` ブランチのみサポート対象です。過去のタグ・ビルドに対するセキュリティ修正のバックポートは行いません。

## 脆弱性の報告

セキュリティに関わる問題は **公開 Issue に投稿しないでください**。
GitHub の [Security Advisories](https://github.com/mohadayo/rag-support-assist/security/advisories/new) 経由で
非公開で報告してください。

### 報告に含めてほしい内容

- 対象コミット SHA / タグ
- 対象領域 (`backend/app/*` / `frontend/src/*` / `docker-compose.yml`)
- 再現手順 (可能なら最小 HTTP リクエスト / 問い合わせ文 / 埋め込みインデックス例)
- 想定される影響 (機密漏洩・改ざん・DoS・プロンプトインジェクション等)
- (任意) 修正案・PoC

24〜72 時間以内に一次応答することを目標とします。

## 脅威モデル

rag-support-assist は FastAPI ベースの RAG バックエンド、Next.js フロントエンド、PostgreSQL + pgvector
のベクトルストアで構成されるカスタマーサポート回答支援 AI です。
以下のカテゴリを主要な脅威として扱います。

1. **プロンプトインジェクション** — 悪意ある問い合わせやドキュメントに埋め込まれた指示によって
   LLM の応答を乗っ取る攻撃 (OWASP LLM01)
2. **機密情報の漏洩** — インデックス化されたドキュメント (顧客対応履歴等) が
   認可されていないクエリ経由で露出する (OWASP LLM06)
3. **入力バリデーション回避** — API に細工リクエストを送りエラー系パスやパーサを崩す
4. **依存パッケージの既知脆弱性** — Python (`pip`) / Node.js (`npm`) / Docker
   ベースイメージ経由の CVE
5. **設定漏洩** — LLM API キー・DB 認証情報のリポジトリ / ログ / イメージへの混入
6. **ネットワーク境界侵害** — pgvector / バックエンドが誤って外部公開ポートに晒される
7. **DoS 相当のリソース枯渇** — 上限のないリクエスト受付・過大なドキュメントアップロード・
   埋め込み計算コスト増大

## 設計上の防御ライン

### 依存パッケージ管理

- Dependabot によって `pip` / `npm` / `github-actions` / `docker` の各エコシステムを週次監視
- CI が Dependabot PR に対しても実行され、互換性を自動検証

### CI ゲート

- Python: `flake8` + `pytest` + `pip-audit` によるライブラリ CVE スキャン
- TypeScript: `eslint` + `next lint` + `vitest` / `jest`
- Docker: `docker compose build`
- 全ジョブが緑になるまで PR をマージしない運用

### アプリケーション境界

- LLM への入力プロンプトは system プロンプトと user プロンプトを明確に分離し、
  ユーザー入力を system プロンプト側に混入させない
- ベクトルストアからの検索結果は、認可されたインデックス (テナント / ユーザー) 内に限定
- API の入力は Pydantic スキーマでバリデーション
- LLM API キー等の秘匿値はプロセス環境変数として注入し、レスポンス・ログには絶対に含めない

### コンテナ境界

- 各サービスは独立した Dockerfile で最小権限イメージを構築
- `docker-compose.yml` で公開ポートを明示的に定義し、意図しないポート露出を防止
- pgvector を含む DB コンテナは compose 内部ネットワークからのみ到達可能

## セキュリティに影響する PR のレビュー観点

以下の変更を含む PR は最低 1 名のセキュリティレビューを必須とします：

- LLM プロンプト構築ロジック (system / user プロンプトの結合部)
- 検索・retrieval のスコープ制御 (テナント境界・ユーザー境界の判定)
- 認証・認可ロジック (API 認可ミドルウェア)
- 入力パーサ・シリアライザ (Pydantic モデル / FastAPI 依存性 / JSON パース)
- 外部通信先 (LLM プロバイダ URL / 埋め込みエンドポイントの URL 生成)
- Docker イメージのベース・実行ユーザ (`USER` 指定) の変更
- `.env` / `docker-compose.yml` の環境変数・ポート追加削除
- CI ワークフロー (`.github/workflows/*.yml`) の権限昇格 (`permissions:` / `secrets:` 追加)

対応するテスト (`backend/tests/*` / `frontend/**/*.test.tsx`) の追加・更新を伴わない
防御ラインの緩和は原則としてマージしません。

## 開発時のシークレット管理

- `.env.example` は雛形のみを含み、実際の値 (LLM API キー・DB 認証情報) は
  各開発者ローカルの `.env` にのみ配置する
- `.env` は `.gitignore` に含まれており、リポジトリにはコミットしない
- 万一シークレット (特に LLM API キー) がコミットされた場合は、直ちに該当キーを
  ローテーションした上で、上記 Security Advisories 経由で報告してください
  (履歴からの完全除去だけでは無効化されません)
