"use client";

import { useState } from "react";
import AnswerDisplay from "@/components/AnswerDisplay";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Source = {
  content: string;
  document_name: string;
  category: string;
  relevance_score: number;
};

type QueryResult = {
  answer: string;
  sources: Source[];
  should_escalate: boolean;
  escalation_reason: string | null;
};

const TONE_OPTIONS = [
  { value: "polite", label: "丁寧" },
  { value: "standard", label: "標準" },
  { value: "concise", label: "簡潔" },
];

export default function Home() {
  const [query, setQuery] = useState("");
  const [tone, setTone] = useState("standard");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), tone }),
      });

      if (!res.ok) {
        throw new Error(`エラーが発生しました (${res.status})`);
      }

      const data: QueryResult = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "不明なエラーが発生しました");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">問い合わせ回答支援</h1>
        <p className="text-sm text-gray-500 mt-1">
          お客様からの問い合わせ内容を入力すると、FAQ・規約・マニュアルを参照して回答候補を生成します。
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="query" className="block text-sm font-medium text-gray-700 mb-1">
            問い合わせ内容
          </label>
          <textarea
            id="query"
            rows={4}
            className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-vertical"
            placeholder="例: 注文した商品が届きません。注文番号は12345です。返金してほしいです。"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              回答トーン
            </label>
            <div className="flex gap-2">
              {TONE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setTone(opt.value)}
                  className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                    tone === opt.value
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1" />

          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors self-end"
          >
            {loading ? "生成中..." : "回答候補を生成"}
          </button>
        </div>
      </form>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-4">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          <span className="ml-3 text-sm text-gray-500">回答候補を生成しています...</span>
        </div>
      )}

      {result && <AnswerDisplay result={result} />}
    </div>
  );
}
