import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "财报可视化分析系统",
  description: "AKShare + FastAPI + Next.js + ECharts",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
