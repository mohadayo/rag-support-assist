# プロンプト設計ガイドライン

rag-support-assist の RAG 回答生成に用いるプロンプトの設計方針と、変更時に確認すべき事項をまとめたドキュメントです。実装は [`backend/app/services/rag.py`](../backend/app/services/rag.py) にあります。

## スコープ

本ドキュメントが対象とするのは、以下のプロンプト・生成パラメータです。

- `SYSTEM_PROMPT` — 回答候補生成のシステムメッセージ
- `TONE_INSTRUCTIONS` — トーン別（`polite` / `standard` / `concise`）の指示文
- `ESCALATION_CHECK_PROMPT` — エスカレーション要否を判定させるプロンプト
- 生成パラメータ: `RAG_MODEL` / `RAG_TEMPERATURE` / `RAG_MAX_TOKENS`

Embedding モデル (`text-embedding-3-small` など) や検索処理（top-K, スコア閾値）は本ドキュメントの範囲外です。それらは [`docs/CONFIGURATION.md`](CONFIGURATION.md) を参照してください。

## プロンプト構造

回答候補生成のリクエストは、Chat Completions API に対して以下の 2 メッセージで構成されます。

```
[system] SYSTEM_PROMPT (トーン指示を埋め込み済み)
[user]   ## 参照文書
         【参照1】(<文書名> / <カテゴリ>)
         <チャンク本文>
         【参照2】...
         ## お客様からの問い合わせ
         <ユーザー入力>
         上記の参照文書を元に回答候補を生成してください。
```

エスカレーション判定は、上記とは別のリクエストで JSON モードを有効化した Chat Completions を呼びます。

```
[system] ESCALATION_CHECK_PROMPT
[user]   問い合わせ: <query>
         回答候補: <生成された回答>
         参照文書: <参照文書テキスト>
```

エスカレーション判定は必ず `response_format={"type": "json_object"}` を指定し、`{"should_escalate": bool, "reason": string|null}` の 2 キーだけを返させます。パースに失敗した場合や例外発生時は、安全側に倒して `should_escalate = True` として扱います。

## SYSTEM_PROMPT の設計原則

| 原則 | 説明 |
| --- | --- |
| 出典限定 | 「提供された参照文書のみを根拠として回答する」ことを明示し、モデルの内部知識に依存させない。 |
| 不明時の明示 | 参照文書に該当がない場合は「該当する情報が見つかりませんでした」と明記させる。曖昧な回答を避け、エスカレーション判定側に安全マージンを渡す。 |
| 推測禁止 | 推測・憶測を明示的に禁止する。ハルシネーションと過剰約束を抑止する目的。 |
| そのまま送れる文面 | 回答をお客様への返信としてそのまま利用できる粒度にする。返信後編集の手間を削減する。 |
| 参照元の付記 | 回答末尾に `---` の後に参照文書名を付記させ、根拠追跡を可能にする。 |
| トーン注入 | 末尾でトーン指示を差し込むテンプレート方式。トーン追加はテンプレートを壊さずに `TONE_INSTRUCTIONS` へ辞書エントリを追加するだけで済む。 |

原則を変更する場合は、必ず [`docs/EVAL.md`](EVAL.md) の評価データセットで回帰を確認してください。とくに「出典限定」と「不明時の明示」を弱めるとハルシネーションの発生率が上がりやすく、Eval 指標のうち Faithfulness と Groundedness の低下として観測されます。

## TONE_INSTRUCTIONS の指針

| トーン | 想定利用シーン | 文体傾向 |
| --- | --- | --- |
| `polite` | 高額返金・クレーム・VIP 顧客対応 | 敬語徹底、配慮表現を厚めに |
| `standard` | 通常の一次回答 | 丁寧さと簡潔さのバランス |
| `concise` | 熟練 CS の下書き、内部確認用 | 要点のみ、箇条書き活用 |

新しいトーンを追加する場合:

1. `TONE_INSTRUCTIONS` に新キーを追加する。値は 1〜2 文の日本語指示にとどめる（トークン消費を抑えるため）。
2. フロントエンド (`frontend/src/app/page.tsx` などの UI) のトーンセレクタに選択肢を追加する。
3. API リクエスト（`POST /api/query` の `tone` フィールド）で受け入れ可能な値として文書化する ([`docs/API.md`](API.md))。
4. Eval データセットに新トーンでの期待出力サンプルを追加する。

`generate_answer` は未知トーンを受け取ると `standard` にフォールバックします。この挙動は API 互換性維持のため、変更しないでください。

## ESCALATION_CHECK_PROMPT の設計

エスカレーション条件は以下の 5 カテゴリに集約しています。

1. 参照文書に十分な根拠がない
2. 法的判断が必要
3. 金額が大きい返金・補償の判断が必要
4. クレームが深刻
5. 個別対応が必要な複雑ケース

このリストを変更する際の注意点:

- カテゴリを **緩める** 変更（例: 「金額が大きい」→ 「特殊」）はエスカレーション漏れを招くため、必ず Eval で False Negative 率を確認する。
- カテゴリを **厳しくする** 変更は False Positive を増やし、CS の負荷を上げる。Eval で誤検知率を確認する。
- JSON スキーマ（`should_escalate` / `reason`）は既存クライアント（`_check_escalation`, UI）の期待値です。キー名や型を変更する場合は、`services/rag.py` の解析ロジックと UI コンポーネントの両方を追随させてください。

失敗時のフォールバックは常に `should_escalate = True` としています。安全側に倒す姿勢は変えないでください。

## 生成パラメータ

| パラメータ | デフォルト | 環境変数 | レンジ | 推奨用途 |
| --- | --- | --- | --- | --- |
| モデル | `gpt-4o-mini` | `RAG_MODEL` | OpenAI 互換モデル ID | 品質を上げたい場合は `gpt-4o`、コスト重視は `gpt-4o-mini` を維持 |
| temperature | `0.3` | `RAG_TEMPERATURE` | `0.0`〜`2.0`（範囲外は無視してデフォルト） | サポート回答は再現性重視。`0.0`〜`0.5` を推奨 |
| max_tokens | `1500` | `RAG_MAX_TOKENS` | `1` 以上（不正値は無視してデフォルト） | 通常回答なら `1500` で十分。長文マニュアル引用が多い場合のみ引き上げる |

`RAG_TEMPERATURE` と `RAG_MAX_TOKENS` のパース失敗・範囲外はいずれもデフォルトへフォールバックします（`_get_temperature` / `_get_max_tokens` 参照）。設定ミスによりサービスが停止することを避けるための安全側の設計であり、この挙動は維持してください。

エスカレーション判定側の温度は常に `0` 固定です。判定の一貫性を最優先しており、環境変数化していません。

## プロンプト変更時のチェックリスト

プロンプトまたは生成パラメータのデフォルトを変更する PR では、以下を必ず確認してください。

- [ ] 変更対象の意図（回答品質改善 / 誤検知抑制 / トーン追加 など）を PR 本文に記載する
- [ ] 変更前後の回答例を最低 3 パターン、可能ならトーン別に添付する
- [ ] [`docs/EVAL.md`](EVAL.md) に従い Eval を実行し、主要指標（Faithfulness / Groundedness / Escalation Precision / Escalation Recall）の回帰を確認する
- [ ] 個人情報（PII）を含むサンプル・実顧客の問い合わせを **プロンプト本文や Eval データセットに含めない**（[`SECURITY.md`](../SECURITY.md) を参照）
- [ ] 参照文書引用フォーマット（末尾の `---` と文書名）を維持する
- [ ] エスカレーション判定 JSON のキー名（`should_escalate` / `reason`）を変更しない（変更する場合は `services/rag.py` と UI を同 PR で更新）
- [ ] `TONE_INSTRUCTIONS` に新キーを追加した場合、`standard` へのフォールバック挙動を壊していないことをユニットテストで確認する
- [ ] トークン消費量が想定内かログで確認する（プロンプト肥大化による課金増を避ける）

## 既知の落とし穴

### 1. 参照文書ゼロ件のガード

`generate_answer` は `context_text` が空文字（空白のみを含む）になった場合、OpenAI API 呼び出しをスキップし、既定のメッセージと `should_escalate = True` を返します。プロンプトを変更した際にこの分岐を壊さないでください。空の参照文書を LLM に渡すと、モデル内部知識で回答してしまい「出典限定」原則を破ります。

### 2. エスカレーション判定の JSON パース失敗

`_check_escalation` は `json.JSONDecodeError` / `KeyError` / `IndexError` および想定外の例外をすべてキャッチし、常に `should_escalate = True` へフォールバックします。この保守的な挙動は明示的な設計であり、簡潔さのために例外処理を外さないでください。

### 3. トーン文言の肥大化

`TONE_INSTRUCTIONS` の各エントリは 1〜2 文にとどめてください。トーン指示が長くなるほど「参照文書を根拠にする」というシステムプロンプトの主張が薄まり、Faithfulness が低下する傾向があります。

### 4. `max_tokens` の過度な引き上げ

`RAG_MAX_TOKENS` を大きくしすぎると、モデルが冗長な回答を生成しやすくなり、CS 担当者の再編集コストが増えます。1500 で足りない場合は、まず参照文書のチャンクサイズ（`docs/CONFIGURATION.md` の `CHUNK_SIZE`）を見直してください。

### 5. temperature を 0 に固定する誘惑

決定性を求めて `temperature = 0` にしたくなりますが、`0.3` は「安定しつつも自然な言い回し」を保つ経験値です。0 まで下げると同一問い合わせに対して常に同じ文面が返り、機械的な印象を与えることがあります。Eval で品質比較を行ったうえで判断してください。

## 関連ドキュメント

- [`docs/API.md`](API.md) — `POST /api/query` のリクエスト・レスポンス仕様（`tone` の受け入れ値、`should_escalate` の扱い）
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — RAG パイプライン全体像と本プロンプトの位置づけ
- [`docs/CONFIGURATION.md`](CONFIGURATION.md) — `RAG_MODEL` / `RAG_TEMPERATURE` / `RAG_MAX_TOKENS` を含む環境変数一覧
- [`docs/EVAL.md`](EVAL.md) — プロンプト変更時の回帰評価手順
- [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 回答が返らない / エスカレーション判定が異常な場合の切り分け
- [`SECURITY.md`](../SECURITY.md) — PII・機密情報の取り扱い方針
