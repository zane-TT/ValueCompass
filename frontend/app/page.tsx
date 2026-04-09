import { AnalysisWorkspace } from "@/components/analysis-workspace";

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
      <AnalysisWorkspace />
    </main>
  );
}
