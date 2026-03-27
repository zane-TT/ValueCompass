import { AnalysisWorkspace } from "@/components/analysis-workspace";

export default function HomePage() {
  return (
    <main className="page-shell">
      <section className="hero">
        <div className="hero-card">
          <div className="eyebrow">Equity Research Agent MVP</div>
          <h1>Read reports. Score quality. Frame value.</h1>
          <p>
            This first version focuses on four practical jobs: extracting key
            financial indicators, detecting accounting risks, generating
            industry-aware valuation commentary, and writing a clean investment
            memo with thesis, risk, and falsification points.
          </p>
        </div>
        <aside className="hero-aside">
          <h2>MVP Coverage</h2>
          <ul className="hero-list">
            <li>Data Agent: normalized statement input and key metrics</li>
            <li>Quality Agent: receivable, inventory, cash flow, goodwill checks</li>
            <li>Valuation Agent: industry-adapted PE / PB / ROE interpretation</li>
            <li>Thesis Agent: memo output with risk review and falsification points</li>
          </ul>
        </aside>
      </section>

      <AnalysisWorkspace />
    </main>
  );
}
