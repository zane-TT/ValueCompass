"use client";

import { useEffect, useState } from "react";
import { AppShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

type StockItem = {
  ticker: string;
  name?: string | null;
};

type BigBetItem = StockItem & {
  maxPortfolioPercent: number;
  ownershipCount: number;
};

type SuperinvestorUpdate = {
  code?: string | null;
  manager: string;
  firm?: string | null;
  updatedAt: string;
  url: string;
};

type InsiderBuy = {
  filedAt: string;
  ticker: string;
  company: string;
  totalValueUsd?: number | null;
  priceUsd?: number | null;
};

type DataromaOverviewResponse = {
  source: string;
  sourceUrl: string;
  fetchedAt: string;
  summary: {
    trackedSuperinvestors?: number | null;
    latestQuarter?: string | null;
  };
  superinvestorUpdates: SuperinvestorUpdate[];
  topOwnedStocks: StockItem[];
  topOwnedByPercent: StockItem[];
  topBigBets: BigBetItem[];
  topBuysLastQuarter: StockItem[];
  topBuysLastQuarterByPercent: StockItem[];
  topBuysLastTwoQuarters: StockItem[];
  insiderBuys: InsiderBuy[];
  notice: string;
};

function formatMoney(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function formatNumber(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function StockList({ title, items }: { title: string; items: StockItem[] }) {
  return (
    <section className="dataroma-panel">
      <div className="dataroma-panel-header">
        <h2>{title}</h2>
      </div>
      <div className="stock-chip-grid">
        {items.length ? (
          items.map((item) => (
            <article key={`${title}-${item.ticker}`} className="stock-chip">
              <strong>{item.ticker}</strong>
              <span>{item.name || "-"}</span>
            </article>
          ))
        ) : (
          <div className="empty-state">No data yet</div>
        )}
      </div>
    </section>
  );
}

export default function SuperinvestorsClient() {
  const [data, setData] = useState<DataromaOverviewResponse | null>(null);
  const [status, setStatus] = useState("Waiting for DATAROMA data");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function loadData(refresh = false) {
    setIsLoading(true);
    setError(null);
    setStatus(refresh ? "Refreshing DATAROMA cache..." : "Loading DATAROMA data...");
    try {
      const params = new URLSearchParams();
      if (refresh) params.set("refresh", "1");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const response = await fetch(`${API_BASE}/api/dataroma/overview${suffix}`);
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const payload = (await response.json()) as { error?: string };
          if (payload.error) message = payload.error;
        } catch {
          // Keep the HTTP status when a proxy returns a non-JSON error body.
        }
        throw new Error(message);
      }
      const payload = (await response.json()) as DataromaOverviewResponse;
      setData(payload);
      setStatus("DATAROMA data loaded");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unknown error");
      setStatus("DATAROMA data failed to load");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const fetchedAt = data?.fetchedAt ? new Date(data.fetchedAt).toLocaleString("en-US") : "-";

  return (
    <AppShell active="superinvestors">
      <section className="dataroma-hero">
        <div>
          <span className="eyebrow-label">DATAROMA / 13F</span>
          <h1>Superinvestor Radar</h1>
          <p>
            A low-frequency research summary from DATAROMA public pages: recent portfolio updates, crowded holdings,
            concentrated bets, and insider buys with direct source links.
          </p>
        </div>
        <div className="dataroma-command">
          <button type="button" onClick={() => void loadData(true)} disabled={isLoading}>
            {isLoading ? "Loading" : "Refresh"}
          </button>
          <a href={data?.sourceUrl || "https://www.dataroma.com/m/home.php"} target="_blank" rel="noreferrer">
            Source
          </a>
        </div>
      </section>

      <section className="dataroma-status-row">
        <article>
          <span>Tracked portfolios</span>
          <strong>{data?.summary.trackedSuperinvestors ?? "-"}</strong>
        </article>
        <article>
          <span>Latest quarter</span>
          <strong>{data?.summary.latestQuarter ?? "-"}</strong>
        </article>
        <article>
          <span>Cached at</span>
          <strong>{fetchedAt}</strong>
        </article>
        <article>
          <span>Status</span>
          <strong>{status}</strong>
        </article>
      </section>

      {error ? <div className="error-box">{error}</div> : null}

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>Recent Portfolio Updates</h2>
          <span>{data?.superinvestorUpdates.length ?? 0} links</span>
        </div>
        <div className="investor-update-grid">
          {(data?.superinvestorUpdates ?? []).map((item) => (
            <a key={`${item.code}-${item.manager}-${item.updatedAt}`} href={item.url} target="_blank" rel="noreferrer" className="investor-update-card">
              <strong>{item.manager}</strong>
              <span>{item.firm || "Independent"}</span>
              <em>{item.updatedAt}</em>
            </a>
          ))}
        </div>
      </section>

      <div className="dataroma-grid">
        <StockList title="Most Owned" items={data?.topOwnedStocks ?? []} />
        <StockList title="Top By Portfolio Weight" items={data?.topOwnedByPercent ?? []} />
        <StockList title="Top Buys Last Quarter" items={data?.topBuysLastQuarter ?? []} />
        <StockList title="Top Buys Last Two Quarters" items={data?.topBuysLastTwoQuarters ?? []} />
      </div>

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>Concentrated Bets</h2>
          <span>Max portfolio weight across tracked investors</span>
        </div>
        <div className="big-bet-table">
          <div className="table-head">
            <span>Stock</span>
            <span>Max weight</span>
            <span>Owners</span>
          </div>
          {(data?.topBigBets ?? []).map((item) => (
            <div key={`big-bet-${item.ticker}`} className="table-row">
              <span>
                <strong>{item.ticker}</strong>
                <em>{item.name}</em>
              </span>
              <span>{formatNumber(item.maxPortfolioPercent)}%</span>
              <span>{item.ownershipCount}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>Insider Buys</h2>
          <span>Related to current superinvestor holdings</span>
        </div>
        <div className="insider-buy-grid">
          {(data?.insiderBuys ?? []).map((item, index) => (
            <article key={`${item.ticker}-${item.filedAt}-${index}`} className="insider-buy-card">
              <span>{item.filedAt}</span>
              <strong>{item.ticker}</strong>
              <em>{item.company || "-"}</em>
              <div>
                <b>{formatMoney(item.totalValueUsd)}</b>
                <small>@ {formatNumber(item.priceUsd)}</small>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="dataroma-disclaimer">
        DATAROMA content is used here as a small research summary with source links. 13F filings can lag actual
        portfolio activity, and this page is not investment advice.
      </section>
    </AppShell>
  );
}
