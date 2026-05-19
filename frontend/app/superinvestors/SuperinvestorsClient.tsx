"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");
type Locale = "zh" | "en";

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

const COPY = {
  zh: {
    waiting: "等待加载 DATAROMA 数据",
    refreshing: "正在刷新 DATAROMA 缓存...",
    loading: "正在加载 DATAROMA 数据...",
    loaded: "DATAROMA 数据已加载",
    failed: "DATAROMA 数据加载失败",
    unknownError: "未知错误",
    noData: "暂无数据",
    heroTitle: "超级投资者持仓雷达",
    heroDesc: "低频抓取 DATAROMA 公开页面摘要，用来观察知名基金经理的组合更新、热门重仓股、集中持仓和内部人买入线索。",
    refresh: "刷新",
    loadingButton: "加载中",
    source: "源站",
    tracked: "追踪组合",
    latestQuarter: "最新季度",
    cachedAt: "缓存时间",
    status: "状态",
    recentUpdates: "最近组合更新",
    links: "条链接",
    viewHoldings: "查看持仓",
    independent: "独立投资者",
    mostOwned: "最多人持有",
    topWeight: "按仓位占比热门",
    topBuysQuarter: "上季度买入",
    topBuysTwoQuarters: "近两个季度买入",
    concentratedBets: "高集中度持仓",
    concentratedHint: "追踪投资人中的最高组合占比",
    stock: "股票",
    maxWeight: "最高仓位",
    owners: "持有人数",
    insiderBuys: "内部人买入",
    insiderHint: "与当前超级投资者持仓相关",
    disclaimer: "DATAROMA 内容在这里仅作为小范围研究摘要展示，并保留源站链接。13F 披露存在滞后，本页不构成投资建议。",
    langLabel: "语言",
  },
  en: {
    waiting: "Waiting for DATAROMA data",
    refreshing: "Refreshing DATAROMA cache...",
    loading: "Loading DATAROMA data...",
    loaded: "DATAROMA data loaded",
    failed: "DATAROMA data failed to load",
    unknownError: "Unknown error",
    noData: "No data yet",
    heroTitle: "Superinvestor Radar",
    heroDesc: "A low-frequency research summary from DATAROMA public pages: recent portfolio updates, crowded holdings, concentrated bets, and insider buys.",
    refresh: "Refresh",
    loadingButton: "Loading",
    source: "Source",
    tracked: "Tracked portfolios",
    latestQuarter: "Latest quarter",
    cachedAt: "Cached at",
    status: "Status",
    recentUpdates: "Recent Portfolio Updates",
    links: "links",
    viewHoldings: "View holdings",
    independent: "Independent",
    mostOwned: "Most Owned",
    topWeight: "Top By Portfolio Weight",
    topBuysQuarter: "Top Buys Last Quarter",
    topBuysTwoQuarters: "Top Buys Last Two Quarters",
    concentratedBets: "Concentrated Bets",
    concentratedHint: "Max portfolio weight across tracked investors",
    stock: "Stock",
    maxWeight: "Max weight",
    owners: "Owners",
    insiderBuys: "Insider Buys",
    insiderHint: "Related to current superinvestor holdings",
    disclaimer: "DATAROMA content is used here as a small research summary with source links. 13F filings can lag actual portfolio activity, and this page is not investment advice.",
    langLabel: "Language",
  },
} satisfies Record<Locale, Record<string, string>>;

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

function StockList({ title, items, emptyText }: { title: string; items: StockItem[]; emptyText: string }) {
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
          <div className="empty-state">{emptyText}</div>
        )}
      </div>
    </section>
  );
}

export default function SuperinvestorsClient() {
  const [locale, setLocale] = useState<Locale>("zh");
  const copy = COPY[locale];
  const [data, setData] = useState<DataromaOverviewResponse | null>(null);
  const [statusKey, setStatusKey] = useState<"waiting" | "refreshing" | "loading" | "loaded" | "failed">("waiting");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function loadData(refresh = false) {
    setIsLoading(true);
    setError(null);
    setStatusKey(refresh ? "refreshing" : "loading");
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
      setStatusKey("loaded");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : copy.unknownError);
      setStatusKey("failed");
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
          <h1>{copy.heroTitle}</h1>
          <p>{copy.heroDesc}</p>
        </div>
        <div className="dataroma-command">
          <div className="locale-switch" aria-label={copy.langLabel}>
            <button type="button" className={locale === "zh" ? "active" : ""} onClick={() => setLocale("zh")}>
              中文
            </button>
            <button type="button" className={locale === "en" ? "active" : ""} onClick={() => setLocale("en")}>
              EN
            </button>
          </div>
          <button type="button" onClick={() => void loadData(true)} disabled={isLoading}>
            {isLoading ? copy.loadingButton : copy.refresh}
          </button>
          <a href={data?.sourceUrl || "https://www.dataroma.com/m/home.php"} target="_blank" rel="noreferrer">
            {copy.source}
          </a>
        </div>
      </section>

      <section className="dataroma-status-row">
        <article>
          <span>{copy.tracked}</span>
          <strong>{data?.summary.trackedSuperinvestors ?? "-"}</strong>
        </article>
        <article>
          <span>{copy.latestQuarter}</span>
          <strong>{data?.summary.latestQuarter ?? "-"}</strong>
        </article>
        <article>
          <span>{copy.cachedAt}</span>
          <strong>{fetchedAt}</strong>
        </article>
        <article>
          <span>{copy.status}</span>
          <strong>{copy[statusKey]}</strong>
        </article>
      </section>

      {error ? <div className="error-box">{error}</div> : null}

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>{copy.recentUpdates}</h2>
          <span>{data?.superinvestorUpdates.length ?? 0} {copy.links}</span>
        </div>
        <div className="investor-update-grid">
          {(data?.superinvestorUpdates ?? []).map((item) => (
            <Link
              key={`${item.code}-${item.manager}-${item.updatedAt}`}
              href={item.code ? `/superinvestors/manager?code=${encodeURIComponent(item.code)}` : item.url}
              className="investor-update-card"
            >
              <strong>{item.manager}</strong>
              <span>{item.firm || copy.independent}</span>
              <em>{item.updatedAt}</em>
              <small>{copy.viewHoldings}</small>
            </Link>
          ))}
        </div>
      </section>

      <div className="dataroma-grid">
        <StockList title={copy.mostOwned} items={data?.topOwnedStocks ?? []} emptyText={copy.noData} />
        <StockList title={copy.topWeight} items={data?.topOwnedByPercent ?? []} emptyText={copy.noData} />
        <StockList title={copy.topBuysQuarter} items={data?.topBuysLastQuarter ?? []} emptyText={copy.noData} />
        <StockList title={copy.topBuysTwoQuarters} items={data?.topBuysLastTwoQuarters ?? []} emptyText={copy.noData} />
      </div>

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>{copy.concentratedBets}</h2>
          <span>{copy.concentratedHint}</span>
        </div>
        <div className="big-bet-table">
          <div className="table-head">
            <span>{copy.stock}</span>
            <span>{copy.maxWeight}</span>
            <span>{copy.owners}</span>
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
          <h2>{copy.insiderBuys}</h2>
          <span>{copy.insiderHint}</span>
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
        {copy.disclaimer}
      </section>
    </AppShell>
  );
}
