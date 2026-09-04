# RAG 品質評価ガイド

`rag-support-assist` (カスタマーサポート回答支援 RAG) の **回答品質・検索品質をどう評価するか** をまとめた軽量ガイド。

- 全体構成は `docs/ARCHITECTURE.md`
- 設定値の意味は `docs/CONFIGURATION.md`
- 障害調査は `docs/TROUBLESHOOTING.md`

本書はパラメータ (`CHUNK_SIZE` / `CHUNK_OVERLAP` / `QUERY_TOP_K` / `RAG_MODEL` など) を触る前後で「本当に良くなったか」を判定できるようにするためのマップである。実装詳細ではなく指針を残す。

## 目次

- [1. なぜ評価するか](#1-なぜ評価するか)
- [2. 何を評価するか (対象レイヤ)](#2-何を評価するか-対象レイヤ)
- [3. メトリクス](#3-メトリクス)
- [4. ゴールデンデータセット](#4-ゴールデンデータセット)
- [5. オフライン評価の実行手順](#5-オフライン評価の実行手順)
- [6. パラメータ変更時のワークフロー](#6-パラメータ変更時のワークフロー)
- [7. アンチパターン](#7-アンチパターン)
- [8. 参考](#8-参考)

## 1. なぜ評価するか

RAG は「取り込み → チャンク → 埋め込み → 検索 → 生成」と段階が多く、体感だけでチューニングすると次の落とし穴に嵌りやすい。

- ある種類の質問は改善したが、別の質問は静かに悪化していた (リグレッション)
- 検索が悪いのか LLM の要約が悪いのかを切り分けられず、原因を誤る
- 本番トラフィックで初めて品質低下に気付く

評価は「変更前後を同じ物差しで比較する」ためにある。完璧な数値化を目指すよりも、**同じ質問集合・同じ物差しで再現できる** ことを優先する。

## 2. 何を評価するか (対象レイヤ)

パイプライン上のどのレイヤの品質を見ているかを常に明示する。層を混ぜて議論すると原因分析ができなくなる。

| レイヤ | 主なコード | 何を測るか |
| :-- | :-- | :-- |
| Retrieval | `services/vectorstore.py` (類似検索) | 正解チャンクが上位に来ているか |
| Generation | `services/rag.py` (LLM 呼び出し) | 与えたコンテキストから忠実な回答を作れているか |
| End-to-End | `routers/query.py` | ユーザー視点で回答は妥当か・出典は正しいか |
| Escalation | `services/rag.py` のエスカレーション判定 | 人へ回すべきときに回し、回さなくてよいときは回さないか |

Retrieval と Generation を **切り離して** 測れるように、評価データセットには「正解チャンク ID」と「期待回答」の両方を含めておくと後で楽になる。

## 3. メトリクス

過剰な数値化を避け、**レイヤごとに最低 1 指標** から始める。慣れてきたら列を足す。

### 3.1 Retrieval

最低限は Recall@k を採用する。`QUERY_TOP_K` を触る議論に直結するため。

| メトリクス | 定義 | いつ使うか |
| :-- | :-- | :-- |
| **Recall@k** | 正解チャンクのうち、上位 k 件に入った割合 | まずこれ。`QUERY_TOP_K` の増減議論に直結 |
| Precision@k | 上位 k 件のうち正解チャンクの割合 | ノイズ (関係ない文書) が混ざる度合いを見たいとき |
| MRR (Mean Reciprocal Rank) | 正解が最初に現れた順位の逆数の平均 | 「1 位に出せているか」を重視したいとき |
| nDCG@k | 順位に重みをつけた関連度スコア | 段階的な関連度を付けた場合の総合指標 |

開始点としては **Recall@5 と MRR の 2 つで十分**。

### 3.2 Generation

Retrieval を固定して、生成部分だけを見る。

| メトリクス | 定義 | 測り方 |
| :-- | :-- | :-- |
| **Faithfulness (根拠一致)** | 回答中の主張が、渡したコンテキストのみから導けるか | 人手 rubric (0-4) または LLM-as-judge |
| **Answer Relevance** | 質問に対して回答がずれていないか | 人手 rubric (0-4) または LLM-as-judge |
| 引用網羅性 | 期待出典 (`relevant_doc_ids`) が回答の `sources` に含まれているか | 期待集合との集合演算 |
| 冗長度 | 余計な前置き・繰り返しの多さ | サンプリングで目視 |

Faithfulness は **ハルシネーション対策の中心指標** である。LLM-as-judge を使う場合でも、初期は 20-30 件を人手で採点し、判定モデルとの一致率を確認してから運用に乗せる。

### 3.3 End-to-End

最終的にユーザーが受け取る品質。次のいずれかを 1 つ選ぶ。

- **人手 rubric (0-4)**: 「4 = 出典に忠実で完全に有用」「0 = 誤りまたは無関係」
- **LLM-as-judge (0-4)**: 上記 rubric を LLM に採点させる。安価だがバイアスに注意

どちらでも、**同じ rubric 文言を使い回すこと** が最重要。物差しが変わると比較不能になる。

### 3.4 Escalation

エスカレーション判定は 2 値分類として扱う。

| メトリクス | 意味 |
| :-- | :-- |
| Escalation Precision | エスカレーションと判定したうち、実際に人が必要だった割合 |
| Escalation Recall | 実際に人が必要だったケースのうち、エスカレーションできた割合 |
| 誤エスカレーション率 (FPR) | 不要なのに人へ回してしまった割合 |
| 見逃し率 (FNR) | 人へ回すべきなのに自動応答してしまった割合 |

見逃し (FNR) の方がユーザー影響が大きいので、Recall を優先目標に置くことが多い。

## 4. ゴールデンデータセット

### 4.1 JSONL スキーマ (例)

1 行 1 質問の JSONL とし、次のフィールドを持つ。

```jsonc
{
  "id": "q-0001",
  "question": "契約プランを月次から年次に変更する手順は?",
  "expected_answer": "設定 > プラン > 年次プランに変更を選択し、決済確認を経て翌請求日から切り替わる。",
  "relevant_doc_ids": ["doc:billing-guide#plan-change", "doc:faq#annual-plan"],
  "must_include": ["年次プラン", "翌請求日"],
  "must_not_include": ["日次プラン"],
  "escalate_expected": false,
  "category": "billing",
  "notes": "料金体系変更 (2026-06) 以降の版"
}
```

- `relevant_doc_ids` … Retrieval 評価の正解集合
- `must_include` / `must_not_include` … Generation 評価の軽量チェック (人手 rubric を待たずに CI で流せる)
- `escalate_expected` … Escalation 評価の正解ラベル
- `category` … カテゴリ別の集計 (billing / account / technical など)
- `notes` … 出典バージョンなど、後で読み返すためのメモ

### 4.2 収集ガイド

- **代表性**: カテゴリ別に均等に集める。1 カテゴリ 10-20 件を目安とし、まずは 50-100 件から始める
- **マスキング**: 実問い合わせを使う場合は氏名・メール・注文番号などを必ず伏字化する (§7 参照)
- **エッジケース**: 「該当情報なし」「複数プランの比較」「エスカレーション必須」などを最低 1 件は含める
- **バージョン管理**: `notes` に出典ドキュメントの版を残し、ドキュメントが更新されたら再評価する
- **格納場所**: リポジトリに含める場合は `backend/tests/data/eval/` を推奨。個人情報を含むケースはリポジトリ外で管理する

## 5. オフライン評価の実行手順

本節は「まず動かす」レベルの最小手順を示す。評価スクリプト自体の追加は別 Issue で扱う。

### 5.1 モックの再利用

`backend/tests/` は既に埋め込み・LLM 呼び出しをモック化してオフラインで動く前提で書かれている (`docs/ARCHITECTURE.md` §6 参照)。評価用にも次を守る。

- 埋め込みモデル・LLM は **本番と同一プロバイダ** を使い、モックは Retrieval を固定する用途に限定する
- 本番 API キーを CI で使う場合は、コスト暴走を防ぐため件数の上限を必ず設ける

### 5.2 最小の実行フロー (擬似コード)

```python
# pytest から呼ぶことを想定した骨格
import json
from app.services import rag, vectorstore, embeddings

def load_cases(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def evaluate_retrieval(case, k):
    vec = embeddings.embed(case["question"])
    hits = vectorstore.similarity_search(vec, k=k)
    hit_ids = {h.doc_id for h in hits}
    relevant = set(case["relevant_doc_ids"])
    recall_at_k = len(hit_ids & relevant) / max(1, len(relevant))
    return {"recall@k": recall_at_k, "hits": list(hit_ids)}

def evaluate_generation(case, answer):
    must_hit = all(s in answer for s in case.get("must_include", []))
    must_miss = all(s not in answer for s in case.get("must_not_include", []))
    return {"must_include_ok": must_hit, "must_not_include_ok": must_miss}
```

### 5.3 結果の出力

CSV または Markdown で残し、コミットする。

```
run_id,ts,git_sha,params,cases,recall@5,mrr,faithfulness_avg,esc_recall,esc_precision,notes
2026-09-04-a,2026-09-04T10:00Z,abc1234,"top_k=5,chunk=500,overlap=100",100,0.82,0.71,3.4,0.90,0.75,baseline
2026-09-04-b,2026-09-04T11:20Z,def5678,"top_k=8,chunk=500,overlap=100",100,0.88,0.74,3.4,0.89,0.72,top_k↑
```

**必ず**

- `git_sha` (どのコードで測ったか)
- `params` (どの設定で測ったか)
- `cases` (何件で測ったか)

の 3 列を残す。これが欠けると再現できなくなる。

## 6. パラメータ変更時のワークフロー

### 6.1 前後比較の型

1. 変更前のパラメータで評価を実行 (baseline)
2. パラメータを変更
3. 同じデータセットで再評価
4. 主要メトリクスを対で並べ、勝ち負けと影響カテゴリを書き残す
5. 改善が明確なら PR に diff を添付してマージ

### 6.2 パラメータと期待される影響 (経験則)

| パラメータ | 上げる | 下げる | 主に効くレイヤ |
| :-- | :-- | :-- | :-- |
| `CHUNK_SIZE` | 文脈が広がり Faithfulness が上がることがある / ノイズと LLM コストも増える | 短い問いへの精度が上がることがある / 文脈不足で誤答が増えることがある | Retrieval / Generation 両方 |
| `CHUNK_OVERLAP` | 境界に落ちる情報を拾えて Recall が上がる / 冗長化とコスト増 | 冗長性は減るが境界情報の取りこぼしが増える | Retrieval |
| `QUERY_TOP_K` | Recall が上がるが Precision と Faithfulness は下がりうる (ノイズ増) | 逆 | Retrieval / Generation 両方 |
| `RAG_MODEL` | 生成品質は上がる傾向 / レイテンシとコストが増える | 逆 | Generation / Escalation |

どれも **上げれば必ず良くなる指標ではない**。必ずゴールデンデータセットで確かめる。

### 6.3 記録の残し方

- `CHANGELOG.md` の該当エントリに `run_id` を書き添える
- 大きな変更 (例: モデル差し替え) は、before/after の抜粋を PR 本文に貼る

## 7. アンチパターン

避けたい典型例。

- **本番問い合わせを平文でリポジトリに置く**: 個人情報リスク。必ずマスキングし、原則リポジトリ外で保管する
- **評価データセットを訓練/プロンプト調整に使ってしまう**: 汚染すると数値が信用できなくなる。評価専用に固定する
- **メトリクスを毎回入れ替える**: 前回と比較不能になる。物差しは動かさない
- **少数ケースで判断する**: 5-10 件では有意差が出ない。せめて 50 件以上、望ましくは 100 件以上
- **LLM-as-judge を人手検証なしで運用する**: 判定モデル自体のバイアスを持ち込む。初期は人手との一致率を確認する
- **エスカレーション判定を Precision だけで見る**: 見逃し (FNR) が上がると実害が大きい。Recall も並べて監視する
- **API キーをテストコードに直書きする**: `SECURITY.md` と `.env.example` の方針に従い、キーは環境変数で渡す

## 8. 参考

- `docs/ARCHITECTURE.md` §3.2 質問応答パイプライン (Query)
- `docs/CONFIGURATION.md` 各設定値の意味 (`CHUNK_SIZE` / `CHUNK_OVERLAP` / `QUERY_TOP_K` / `RAG_MODEL`)
- `docs/TROUBLESHOOTING.md` 品質低下時の切り分け
- `backend/app/services/{chunker,embeddings,vectorstore,rag}.py` 実装本体
- `backend/tests/` オフラインで動くテストのモック機構

## 変更履歴

- 2026-09-04: 初版作成。
