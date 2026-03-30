"use client";

import { useState } from "react";
import SourceCard from "./SourceCard";

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

export default function AnswerDisplay({ result }: { result: QueryResult }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(result.answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-4">
      {/* エスカレーション警告 */}
      {result.should_escalate && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-4">
          <div className="flex items-center gap-2 text-amber-800 font-medium text-sm">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            エスカレーション推奨
          </div>
          {result.escalation_reason && (
            <p className="text-sm text-amber-700 mt-1">{result.escalation_reason}</p>
          )}
        </div>
      )}

      {/* 回答候補 */}
      <div className="bg-white border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
          <h2 className="font-medium text-gray-800">回答候補</h2>
          <button
            onClick={handleCopy}
            className="text-sm px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            {copied ? "コピーしました" : "コピー"}
          </button>
        </div>
        <div className="p-4 whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
          {result.answer}
        </div>
      </div>

      {/* 参照ソース */}
      {result.sources.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-600 mb-2">
            参照した根拠文書 ({result.sources.length}件)
          </h3>
          <div className="space-y-2">
            {result.sources.map((source, i) => (
              <SourceCard key={i} source={source} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
