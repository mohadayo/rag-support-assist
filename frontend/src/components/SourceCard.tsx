"use client";

type Source = {
  content: string;
  document_name: string;
  category: string;
  relevance_score: number;
};

const CATEGORY_LABELS: Record<string, string> = {
  faq: "FAQ",
  terms: "利用規約",
  manual: "マニュアル",
  history: "過去問い合わせ",
};

export default function SourceCard({ source }: { source: Source }) {
  const score = Math.round(source.relevance_score * 100);
  const scoreColor =
    score >= 70 ? "text-green-700 bg-green-50" : score >= 40 ? "text-yellow-700 bg-yellow-50" : "text-red-700 bg-red-50";

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-white">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
            {CATEGORY_LABELS[source.category] || source.category}
          </span>
          <span className="text-sm font-medium text-gray-700">
            {source.document_name}
          </span>
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${scoreColor}`}>
          関連度 {score}%
        </span>
      </div>
      <p className="text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">
        {source.content}
      </p>
    </div>
  );
}
