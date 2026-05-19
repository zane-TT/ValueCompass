"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

type ActivityType = "buy" | "add" | "reduce" | "sell" | "hold";

type Activity = {
  type: ActivityType;
  label: string;
  percent?: number | null;
};

type Holding = {
  ticker: string;
  name: string;
  portfolioPercent: number;
  recentActivity: Activity;
  shares?: number | null;
  value?: number | null;
};

type ActivityItem = {
  ticker: string;
  name: string;
  activity: Activity;
  shareChange?: number | null;
  portfolioImpactPercent?: number | null;
};

type ActivityQuarter = {
  quarter?: string | null;
  items: ActivityItem[];
};

type ManagerPayload = {
  managerCode: string;
  manager: string;
  firm?: string | null;
  sourceUrl: string;
  fetchedAt: string;
  period?: string | null;
  portfolioDate?: string | null;
  reportedStockCount?: number | null;
  portfolioValue?: number | null;
  concentration: {
    top1Percent?: number | null;
    top5Percent?: number | null;
    top10Percent?: number | null;
    holdingCount: number;
  };
  holdings: Holding[];
  topHoldings: Holding[];
  activityByQuarter: ActivityQuarter[];
  latestActivitySummary: Record<"buy" | "add" | "reduce" | "sell", number>;
  latestActivityItems: ActivityItem[];
  notice: string;
};

function formatMoney(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function formatNumber(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatShares(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("en-US");
}

function actionTone(type?: ActivityType) {
  if (type === "buy" || type === "add") return "positive";
  if (type === "reduce") return "warning";
  if (type === "sell") return "danger";
  return "neutral";
}

function ActivityBadge({ activity }: { activity: Activity }) {
  if (!activity.label) return <span className="activity-badge neutral">Hold</span>;
  return <span className={`activity-badge ${actionTone(activity.type)}`}>{activity.label}</span>;
}

function SummaryMetric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </article>
  );
}

function ManagerDetailContent() {
  const searchParams = useSearchParams();
  const managerCode = searchParams.get("code")?.trim() || "BRK";
  const [data, setData] = useState<ManagerPayload | null>(null);
  const [status, setStatus] = useState("Waiting for manager data");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function loadData(refresh = false) {
    setIsLoading(true);
    setError(null);
    setStatus(refresh ? "Refreshing manager cache..." : "Loading manager data...");
    try {
      const params = new URLSearchParams({ manager: managerCode });
      if (refresh) params.set("refresh", "1");
      const response = await fetch(`${API_BASE}/api/dataroma/manager?${params.toString()}`);
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const payload = (await response.json()) as { error?: string };
          if (payload.error) message = payload.error;
        } catch {
          // Keep the HTTP status when the backend returns a non-JSON body.
        }
        throw new Error(message);
      }
      const payload = (await response.json()) as ManagerPayload;
      setData(payload);
      setStatus(payload.period ? `${payload.period} portfolio loaded` : "Manager data loaded");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unknown error");
      setStatus("Manager data failed to load");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [managerCode]);

  const groupedActivity = useMemo(() => {
    const groups: Record<"buy" | "add" | "reduce" | "sell", ActivityItem[]> = {
      buy: [],
      add: [],
      reduce: [],
      sell: [],
    };
    for (const item of data?.latestActivityItems ?? []) {
      if (item.activity.type in groups) groups[item.activity.type as keyof typeof groups].push(item);
    }
    return groups;
  }, [data?.latestActivityItems]);

  const maxWeight = data?.topHoldings.reduce((max, item) => Math.max(max, item.portfolioPercent), 0) || 1;
  const fetchedAt = data?.fetchedAt ? new Date(data.fetchedAt).toLocaleString("en-US") : "-";

  return (
    <AppShell active="superinvestors">
      <section className="manager-hero">
        <div>
          <Link className="back-link" href="/superinvestors">
            Superinvestors
          </Link>
          <span className="eyebrow-label">DATAROMA / MANAGER</span>
          <h1>{data?.manager || managerCode}</h1>
          <p>{data?.firm || "Portfolio holdings and quarterly activity summary."}</p>
        </div>
        <div className="dataroma-command">
          <button type="button" onClick={() => void loadData(true)} disabled={isLoading}>
            {isLoading ? "Loading" : "Refresh"}
          </button>
          <a href={data?.sourceUrl || `https://www.dataroma.com/m/holdings.php?m=${managerCode}`} target="_blank" rel="noreferrer">
            Source
          </a>
        </div>
      </section>

      <section className="manager-summary-grid">
        <SummaryMetric label="Portfolio value" value={formatMoney(data?.portfolioValue)} detail={data?.period || undefined} />
        <SummaryMetric label="Holdings" value={formatNumber(data?.reportedStockCount ?? data?.concentration.holdingCount, 0)} detail={data?.portfolioDate || undefined} />
        <SummaryMetric label="Top 5 weight" value={`${formatNumber(data?.concentration.top5Percent)}%`} detail={`Top 1: ${formatNumber(data?.concentration.top1Percent)}%`} />
        <SummaryMetric label="Latest activity" value={`${data?.latestActivitySummary.buy ?? 0} buy / ${data?.latestActivitySummary.add ?? 0} add`} detail={`${data?.latestActivitySummary.reduce ?? 0} reduce / ${data?.latestActivitySummary.sell ?? 0} sell`} />
        <SummaryMetric label="Cached at" value={fetchedAt} detail={status} />
      </section>

      {error ? <div className="error-box">{error}</div> : null}

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>Top Holdings</h2>
          <span>Position weight in reported 13F portfolio</span>
        </div>
        <div className="holding-weight-list">
          {(data?.topHoldings ?? []).map((item) => (
            <article key={`top-${item.ticker}`} className="holding-weight-row">
              <div>
                <strong>{item.ticker}</strong>
                <span>{item.name}</span>
              </div>
              <div className="weight-bar" aria-label={`${item.ticker} weight ${formatNumber(item.portfolioPercent)} percent`}>
                <i style={{ width: `${Math.max(4, (item.portfolioPercent / maxWeight) * 100)}%` }} />
              </div>
              <b>{formatNumber(item.portfolioPercent)}%</b>
            </article>
          ))}
        </div>
      </section>

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>Quarterly Activity</h2>
          <span>{data?.activityByQuarter[0]?.quarter || "Latest quarter"}</span>
        </div>
        <div className="activity-group-grid">
          {(["buy", "add", "reduce", "sell"] as const).map((type) => (
            <article key={type} className={`activity-group ${actionTone(type)}`}>
              <h3>{type.toUpperCase()}</h3>
              {groupedActivity[type].length ? (
                groupedActivity[type].slice(0, 8).map((item) => (
                  <div key={`${type}-${item.ticker}`} className="activity-item-row">
                    <strong>{item.ticker}</strong>
                    <span>{item.name}</span>
                    <em>{item.activity.label}</em>
                  </div>
                ))
              ) : (
                <p>No items</p>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>Full Holdings</h2>
          <span>{data?.holdings.length ?? 0} rows</span>
        </div>
        <div className="manager-holdings-table">
          <div className="manager-holdings-head">
            <span>Stock</span>
            <span>Weight</span>
            <span>Activity</span>
            <span>Shares</span>
            <span>Value</span>
          </div>
          {(data?.holdings ?? []).map((item) => (
            <div key={`holding-${item.ticker}`} className="manager-holdings-row">
              <span>
                <strong>{item.ticker}</strong>
                <em>{item.name}</em>
              </span>
              <span>{formatNumber(item.portfolioPercent)}%</span>
              <span>
                <ActivityBadge activity={item.recentActivity} />
              </span>
              <span>{formatShares(item.shares)}</span>
              <span>{formatMoney(item.value)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="dataroma-disclaimer">
        {data?.notice ||
          "DATAROMA content is shown as a small research summary with source links. 13F filings are delayed and this page is not investment advice."}
      </section>
    </AppShell>
  );
}

export default function ManagerDetailClient() {
  return (
    <Suspense fallback={<div className="status-line">Loading manager route...</div>}>
      <ManagerDetailContent />
    </Suspense>
  );
}
