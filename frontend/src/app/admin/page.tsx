"use client";

import { useState, useEffect, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type DocumentInfo = {
  id: string;
  name: string;
  category: string;
  chunk_count: number;
  uploaded_at: string;
};

const CATEGORY_OPTIONS = [
  { value: "faq", label: "FAQ" },
  { value: "terms", label: "利用規約" },
  { value: "manual", label: "マニュアル" },
  { value: "history", label: "過去問い合わせ" },
];

const CATEGORY_LABELS: Record<string, string> = {
  faq: "FAQ",
  terms: "利用規約",
  manual: "マニュアル",
  history: "過去問い合わせ",
};

export default function AdminPage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [category, setCategory] = useState("faq");
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents);
      }
    } catch {
      // サーバー未起動時は無視
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const file = formData.get("file") as File;
    if (!file || !file.name) return;

    setUploading(true);
    setMessage(null);

    const uploadData = new FormData();
    uploadData.append("file", file);
    uploadData.append("category", category);

    try {
      const res = await fetch(`${API_URL}/api/documents/upload`, {
        method: "POST",
        body: uploadData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "アップロードに失敗しました");
      }

      const doc = await res.json();
      setMessage({
        type: "success",
        text: `「${doc.name}」をアップロードしました（${doc.chunk_count}チャンク）`,
      });
      fetchDocuments();
      e.currentTarget.reset();
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "エラーが発生しました",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId: string, docName: string) => {
    if (!confirm(`「${docName}」を削除しますか？`)) return;

    try {
      const res = await fetch(`${API_URL}/api/documents/${docId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setMessage({ type: "success", text: `「${docName}」を削除しました` });
        fetchDocuments();
      }
    } catch {
      setMessage({ type: "error", text: "削除に失敗しました" });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">文書管理</h1>
        <p className="text-sm text-gray-500 mt-1">
          FAQ・利用規約・マニュアル・過去問い合わせをアップロードして管理できます。
        </p>
      </div>

      {/* アップロードフォーム */}
      <form
        onSubmit={handleUpload}
        className="bg-white border border-gray-200 rounded-lg p-6 space-y-4"
      >
        <h2 className="font-medium text-gray-800">文書アップロード</h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              ファイル (.txt / .md / .csv)
            </label>
            <input
              type="file"
              name="file"
              accept=".txt,.md,.csv"
              required
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              カテゴリ
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="submit"
          disabled={uploading}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {uploading ? "アップロード中..." : "アップロード"}
        </button>
      </form>

      {/* メッセージ */}
      {message && (
        <div
          className={`text-sm rounded-lg p-4 ${
            message.type === "success"
              ? "bg-green-50 border border-green-200 text-green-700"
              : "bg-red-50 border border-red-200 text-red-700"
          }`}
        >
          {message.text}
        </div>
      )}

      {/* 文書一覧 */}
      <div>
        <h2 className="font-medium text-gray-800 mb-3">
          登録済み文書 ({documents.length}件)
        </h2>
        {documents.length === 0 ? (
          <p className="text-sm text-gray-500 bg-white border border-gray-200 rounded-lg p-8 text-center">
            文書が登録されていません。上のフォームからアップロードしてください。
          </p>
        ) : (
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">文書名</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">カテゴリ</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">チャンク数</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-800">{doc.name}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs font-medium bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                        {CATEGORY_LABELS[doc.category] || doc.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">{doc.chunk_count}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleDelete(doc.id, doc.name)}
                        className="text-red-600 hover:text-red-800 text-xs font-medium"
                      >
                        削除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
