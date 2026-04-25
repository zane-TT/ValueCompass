import { AnalysisWorkspace } from "@/components/analysis-workspace";
import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page-shell">
      <section className="page-topbar">
        <div>
          <div className="eyebrow">ValueCompass</div>
          <h1 className="page-title">Research terminal for stocks, risk, and agent tools.</h1>
        </div>
        <div className="topbar-note">
          <strong>MVP</strong>
          <span>Deterministic analysis + LangChain tool-calling demo in one surface.</span>
        </div>
      </section>
      <section style={{ padding: "20px", borderBottom: "1px solid #eee" }}>
        <Link
          href="/financial-history"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "12px 24px",
            backgroundColor: "#5470c6",
            color: "white",
            borderRadius: "8px",
            textDecoration: "none",
            fontWeight: 500,
          }}
        >
          📊 财务历史分析 - PE与营收对比图表
        </Link>
      </section>
      <AnalysisWorkspace />
    </main>
  );
}
