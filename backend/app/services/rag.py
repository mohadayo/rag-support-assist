"""RAG回答生成サービス"""

import json
import logging
import os
import time

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1500"))
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "30"))

_client: OpenAI | None = None

TONE_INSTRUCTIONS = {
    "polite": "非常に丁寧で敬語を徹底した文体で回答してください。お客様への配慮を最大限に示してください。",
    "concise": "簡潔で要点のみを伝える文体で回答してください。箇条書きを活用してください。",
    "standard": "標準的なビジネス文体で回答してください。丁寧さと簡潔さのバランスを取ってください。",
}

SYSTEM_PROMPT = """あなたはカスタマーサポートの回答支援AIです。
以下のルールに従って回答候補を生成してください。

## ルール
1. 提供された参照文書のみを根拠として回答すること
2. 参照文書に該当する情報がない場合は「該当する情報が見つかりませんでした」と明記すること
3. 推測や憶測は行わないこと
4. 回答はそのままお客様への返信として使えるレベルの文面にすること
5. 回答の最後に「---」の後に参照した文書名を記載すること

## トーン指示
{tone_instruction}
"""

ESCALATION_CHECK_PROMPT = """以下の問い合わせと回答候補について、エスカレーションが必要か判断してください。

エスカレーションが必要な場合:
- 参照文書に十分な根拠がない場合
- 法的判断が必要な場合
- 金額が大きい返金・補償の判断が必要な場合
- クレームが深刻な場合
- 個別対応が必要な複雑なケース

JSON形式で回答してください:
{{"should_escalate": true/false, "reason": "理由（不要ならnull）"}}
"""


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
        logger.info("OpenAIクライアントを初期化しました (model=%s)", OPENAI_MODEL)
    return _client


def generate_answer(
    query: str,
    contexts: list[dict],
    tone: str = "standard",
) -> tuple[str, bool, str | None]:
    """RAGで回答候補を生成する

    Returns:
        (回答テキスト, エスカレーション要否, エスカレーション理由)
    """
    client = get_client()
    tone_instruction = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["standard"])

    # コンテキスト文書の構築
    context_text = ""
    for i, ctx in enumerate(contexts, 1):
        context_text += f"\n【参照{i}】({ctx['document_name']} / {ctx['category']})\n{ctx['content']}\n"

    if not context_text.strip():
        return (
            "申し訳ございませんが、登録されている文書に該当する情報が見つかりませんでした。\n担当者へのエスカレーションをお勧めします。",
            True,
            "参照可能な文書が登録されていません",
        )

    # 回答生成
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(tone_instruction=tone_instruction),
        },
        {
            "role": "user",
            "content": f"## 参照文書\n{context_text}\n\n## お客様からの問い合わせ\n{query}\n\n上記の参照文書を元に回答候補を生成してください。",
        },
    ]

    logger.info(
        "回答生成リクエスト: model=%s, tone=%s, contexts=%d件, temperature=%.1f, max_tokens=%d",
        OPENAI_MODEL, tone, len(contexts), OPENAI_TEMPERATURE, OPENAI_MAX_TOKENS,
    )

    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
            timeout=OPENAI_TIMEOUT,
        )
    except OpenAIError as e:
        elapsed = time.time() - start_time
        logger.error("回答生成中にOpenAIエラーが発生: error=%s, elapsed=%.2fs", e, elapsed)
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception("回答生成中に予期しないエラーが発生: error=%s, elapsed=%.2fs", e, elapsed)
        raise

    elapsed = time.time() - start_time
    usage = response.usage
    logger.info(
        "回答生成LLM応答: elapsed=%.2fs, prompt_tokens=%d, completion_tokens=%d, total_tokens=%d",
        elapsed,
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
        usage.total_tokens if usage else 0,
    )
    answer = response.choices[0].message.content

    # エスカレーション判定
    should_escalate, reason = _check_escalation(client, query, answer, context_text)

    logger.info("回答生成完了: escalate=%s, total_elapsed=%.2fs", should_escalate, time.time() - start_time)
    return answer, should_escalate, reason


def _check_escalation(
    client: OpenAI,
    query: str,
    answer: str,
    context_text: str,
) -> tuple[bool, str | None]:
    """エスカレーション要否を判定する"""
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": ESCALATION_CHECK_PROMPT},
                {
                    "role": "user",
                    "content": f"問い合わせ: {query}\n\n回答候補: {answer}\n\n参照文書: {context_text}",
                },
            ],
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"},
            timeout=OPENAI_TIMEOUT,
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("should_escalate", False), result.get("reason")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("エスカレーション判定のレスポンス解析に失敗: %s", e)
        return True, "エスカレーション判定でエラーが発生したため、安全のためエスカレーションを推奨"
    except Exception:
        logger.exception("エスカレーション判定中に予期しないエラーが発生")
        return True, "エスカレーション判定でエラーが発生したため、安全のためエスカレーションを推奨"
