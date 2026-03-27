"use client";

import { useEffect, useState } from "react";

type SampleTicker = {
  ticker: string;
  name: string;
};

type AnalysisResponse = {
  company: {
    ticker: string;
    name: string;
    industry: string;
    description: string;
  };
  metrics: Array<{
    label: string;
    value: string;
    interpretation: string;
  }>;
  quality_score: number;
  valuation_stance: string;
  margin_of_safety: string;
  risk_flags: Array<{
    level: "low" | "medium" | "high";
    title: string;
    detail: string;
  }>;
  memo: Array<{
    title: string;
    body: string;
  }>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function AnalysisWorkspace() {
  const [ticker, setTicker] = useState("600519");
  const [sampleTickers, setSampleTickers] = useState<SampleTicker[]>([]);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const loadSamples = async () => {
      try {
        const res = await fetch(`${API_BASE}/sample-tickers`);
        if (!res.ok) {
          throw new Error("Failed to load sample tickers.");
        }
        const data = (await res.json()) as SampleTicker[];
        setSampleTickers(data);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Unable to load samples.");
      }
    };

    loadSamples();
  }, []);

  const analyze = async (nextTicker?: string) => {
    const target = nextTicker ?? ticker;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ ticker: target })
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Analysis failed.");
      }

      const data = (await res.json()) as AnalysisResponse;
      setTicker(target);
      setResult(data);
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : "Analysis failed.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void analyze("600519");
  }, []);

  return (
    <section className="grid">
      <aside className="panel">
        <h2>Run Analysis</h2>
        <div className="form-stack">
          <label className="label">
            Ticker
            <input
              className="input"
              value={ticker}
              onChange={(event) => setTicker(event.target.value)}
              placeholder="Enter ticker"
            />
          </label>

          <div className="button-row">
            <button className="button primary" onClick={() => void analyze()} disabled={loading}>
              {loading ? "Analyzing..." : "Analyze"}
            </button>
          </div>

          <div className="hint">
            Current MVP includes built-in sample data. Start with a sample ticker
            and replace the data connector later.
          </div>

          <ul className="meta-list">
            {sampleTickers.map((item) => (
              <li key={item.ticker}>
                <strong>{item.ticker}</strong> {item.name}
                <div style={{ marginTop: 10 }}>
                  <button
                    className="button secondary"
                    onClick={() => void analyze(item.ticker)}
                    disabled={loading}
                  >
                    Load sample
                  </button>
                </div>
              </li>
            ))}
          </ul>

          {error ? <div className="risk-item">{error}</div> : null}
        </div>
      </aside>

      <div className="results">
        {result ? <AnalysisResults result={result} /> : <div className="empty-state">Analysis output will appear here.</div>}
      </div>
    </section>
  );
}

function AnalysisResults({ result }: { result: AnalysisResponse }) {
  return (
    <>
      <section className="result-card">
        <div className="result-header">
          <div>
            <div className="eyebrow">{result.company.ticker}</div>
            <h2>{result.company.name}</h2>
            <p className="muted">{result.company.description}</p>
          </div>
          <div className="score-pill">Quality Score {result.quality_score}</div>
        </div>
      </section>

      <section className="result-card">
        <h3>Key Metrics</h3>
        <div className="metrics-grid" style={{ marginTop: 16 }}>
          {result.metrics.map((metric) => (
            <article className="metric" key={metric.label}>
              <div className="muted">{metric.label}</div>
              <div className="value">{metric.value}</div>
              <div className="muted">{metric.interpretation}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="result-card">
        <h3>Valuation Framing</h3>
        <div className="memo-grid" style={{ marginTop: 16 }}>
          <article className="memo-section">
            <h3>Valuation Stance</h3>
            <p className="muted">{result.valuation_stance}</p>
          </article>
          <article className="memo-section">
            <h3>Margin of Safety</h3>
            <p className="muted">{result.margin_of_safety}</p>
          </article>
        </div>
      </section>

      <section className="result-card">
        <h3>Risk Flags</h3>
        <div className="risk-list" style={{ marginTop: 16 }}>
          {result.risk_flags.length === 0 ? (
            <div className="risk-item">No major accounting-quality flags were triggered by the current sample logic.</div>
          ) : (
            result.risk_flags.map((risk) => (
              <article className="risk-item" key={`${risk.level}-${risk.title}`}>
                <div className={`risk-pill ${risk.level}`}>{risk.level.toUpperCase()}</div>
                <h3 style={{ marginTop: 12 }}>{risk.title}</h3>
                <p className="muted">{risk.detail}</p>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="result-card">
        <h3>Investment Memo</h3>
        <div className="memo-grid" style={{ marginTop: 16 }}>
          {result.memo.map((section) => (
            <article className="memo-section" key={section.title}>
              <h3>{section.title}</h3>
              <p className="muted">{section.body}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
