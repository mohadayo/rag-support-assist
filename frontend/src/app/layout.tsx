import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG Support Assist",
  description: "カスタマーサポート回答支援AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="bg-gray-50 text-gray-900 min-h-screen">
        <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          <a href="/" className="text-lg font-bold text-blue-700">
            RAG Support Assist
          </a>
          <nav className="flex gap-4 text-sm">
            <a href="/" className="hover:text-blue-600">
              問い合わせ
            </a>
            <a href="/admin" className="hover:text-blue-600">
              管理画面
            </a>
          </nav>
        </header>
        <main className="max-w-5xl mx-auto p-6">{children}</main>
      </body>
    </html>
  );
}
