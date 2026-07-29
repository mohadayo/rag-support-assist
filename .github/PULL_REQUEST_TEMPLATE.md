## 変更概要

<!-- 何を変更したか簡潔に記述してください -->

-
-

## 対応 Issue

<!-- 例: Closes #123 / Refs #45 -->

Closes #

## 影響範囲

<!-- 該当するものにチェック -->

- [ ] `backend/`（FastAPI / retriever / LLM 連携）
- [ ] `frontend/`（React アプリ）
- [ ] `sample_data/`（サンプルドキュメント）
- [ ] `docker-compose.yml`
- [ ] ドキュメント / CI 設定のみ
- [ ] その他:

## 動作確認手順

<!-- レビュアーが再現できる粒度で記載 -->

1.
2.
3.

## チェックリスト

- [ ] `pytest` がローカルでパスすること（`backend/tests/`）
- [ ] `bandit -r app/ -ll -ii` で新規高/中リスクが出ていない
- [ ] `pip-audit --requirement requirements.txt` で新規脆弱性が出ていない
- [ ] 環境変数追加時は `.env.example`（もしできるなら backend/README）を更新済み

## 補足

<!-- スクリーンショット・関連リンクなど -->
