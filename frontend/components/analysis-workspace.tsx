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

type AgentDemoResponse = {
  answer: string;
  model: string;
  tool_calls: Array<{
    name: string;
    args: Record<string, unknown>;
    result: Record<string, unknown> | Array<unknown> | string;
  }>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const DEFAULT_AGENT_PROMPT =
  "Please classify the company, find peers, and tell me whether the valuation should be compared on quality or assets.";

export function AnalysisWorkspace() {
  const [ticker, setTicker] = useState("600519");
  const [sampleTickers, setSampleTickers] = useState<SampleTicker[]>([]);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResponse | null>(null);
  const [agentResult, setAgentResult] = useState<AgentDemoResponse | null>(null);
  const [agentPrompt, setAgentPrompt] = useState(DEFAULT_AGENT_PROMPT);
  const [error, setError] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [agentLoading, setAgentLoading] = useState(false);

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
    setAnalysisLoading(true);
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
      setAnalysisResult(data);
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : "Analysis failed.");
    } finally {
      setAnalysisLoading(false);
    }
  };

  const runAgentDemo = async (nextTicker?: string) => {
    const target = nextTicker ?? ticker;
    setAgentLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/agent-demo`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          ticker: target,
          question: agentPrompt
        })
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Agent demo failed.");
      }

      const data = (await res.json()) as AgentDemoResponse;
      setTicker(target);
      setAgentResult(data);
    } catch (agentError) {
      setError(agentError instanceof Error ? agentError.message : "Agent demo failed.");
    } finally {
      setAgentLoading(false);
    }
  };

  useEffect(() => {
    void analyze("600519");
  }, []);

  return (
    <section className="workspace-shell">
      <aside className="control-rail">
        <section className="panel control-panel">
          <div className="eyebrow">Control Center</div>
          <h2>Research Workspace</h2>
          <div className="form-stack">
            <label className="label">
              Target ticker
              <input
                className="input"
                value={ticker}
                onChange={(event) => setTicker(event.target.value)}
                placeholder="Enter ticker"
              />
            </label>

            <div className="button-row">
              <button className="button primary" onClick={() => void analyze()} disabled={analysisLoading}>
                {analysisLoading ? "Analyzing..." : "Run MVP Analysis"}
              </button>
              <button className="button secondary" onClick={() => void runAgentDemo()} disabled={agentLoading}>
                {agentLoading ? "Running agent..." : "Run LangChain Demo"}
              </button>
            </div>

            <div className="hint">
              The left rail is for operations. The right side is the actual
              research output surface.
            </div>
          </div>
        </section>

        <section className="panel control-panel">
          <div className="eyebrow">Agent Prompt</div>
          <h2>Tool-Calling Demo</h2>
          <label className="label">
            Question for the agent
            <textarea
              className="input textarea"
              value={agentPrompt}
              onChange={(event) => setAgentPrompt(event.target.value)}
            />
          </label>
        </section>

        <section className="panel control-panel">
          <div className="eyebrow">Sample Universe</div>
          <h2>Quick Load</h2>
          <ul className="meta-list">
            {sampleTickers.map((item) => (
              <li key={item.ticker}>
                <strong>{item.ticker}</strong> {item.name}
                <div className="button-row" style={{ marginTop: 10 }}>
                  <button className="button secondary" onClick={() => void analyze(item.ticker)} disabled={analysisLoading}>
                    Analysis
                  </button>
                  <button className="button secondary" onClick={() => void runAgentDemo(item.ticker)} disabled={agentLoading}>
                    Agent
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {error ? <div className="risk-item">{error}</div> : null}
        </section>
      </aside>

      <div className="content-stage">
        <section className="workspace-summary">
          <div className="summary-card">
            <div className="eyebrow">ValueCompass</div>
            <h2>Two parallel surfaces</h2>
            <p className="muted">
              The left side drives the workflow. The right side lets you compare
              deterministic research output with LLM-orchestrated tool usage.
            </p>
          </div>
          <div className="summary-grid">
            <div className="summary-stat">
              <span className="summary-label">MVP Mode</span>
              <strong>Financial quality + memo</strong>
            </div>
            <div className="summary-stat">
              <span className="summary-label">Agent Mode</span>
              <strong>LangChain + OpenAI tool calling</strong>
            </div>
          </div>
        </section>

        <section className="dual-results">
          <div className="results-column">
            <div className="column-header">
              <div>
                <div className="eyebrow">Deterministic Pipeline</div>
                <h2>MVP Analysis</h2>
              </div>
            </div>
            {analysisResult ? (
              <AnalysisResults result={analysisResult} />
            ) : (
              <div className="empty-state">MVP analysis output will appear here.</div>
            )}
          </div>

          <div className="results-column">
            <div className="column-header">
              <div>
                <div className="eyebrow">Agent Orchestration</div>
                <h2>LangChain Demo</h2>
              </div>
            </div>
            {agentResult ? (
              <AgentDemoResults result={agentResult} />
            ) : (
              <div className="empty-state">LangChain tool-calling output will appear here.</div>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function AnalysisResults({ result }: { result: AnalysisResponse }) {
  return (
    <div className="results">
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
    </div>
  );
}

function AgentDemoResults({ result }: { result: AgentDemoResponse }) {
  return (
    <div className="results">
      <section className="result-card">
        <div className="result-header">
          <div>
            <div className="eyebrow">OpenAI Model</div>
            <h2>{result.model}</h2>
            <p className="muted">
              This panel shows how the model selected atomic tools and then
              synthesized a final answer.
            </p>
          </div>
          <div className="score-pill">Tool calls {result.tool_calls.length}</div>
        </div>
      </section>

      <section className="result-card">
        <h3>Final Answer</h3>
        <article className="memo-section" style={{ marginTop: 16 }}>
          <p className="muted">{result.answer}</p>
        </article>
      </section>

      <section className="result-card">
        <h3>Tool Calls</h3>
        <div className="tool-call-list" style={{ marginTop: 16 }}>
          {result.tool_calls.length === 0 ? (
            <div className="risk-item">The model answered without calling tools.</div>
          ) : (
            result.tool_calls.map((toolCall, index) => (
              <article className="tool-card" key={`${toolCall.name}-${index}`}>
                <div className="tool-card-header">
                  <strong>{toolCall.name}</strong>
                  <span className="tool-seq">#{index + 1}</span>
                </div>
                <div className="tool-block">
                  <div className="tool-label">Args</div>
                  <pre>{JSON.stringify(toolCall.args, null, 2)}</pre>
                </div>
                <div className="tool-block">
                  <div className="tool-label">Result</div>
                  <pre>{JSON.stringify(toolCall.result, null, 2)}</pre>
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
