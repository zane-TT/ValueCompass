"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");
type Locale = "zh" | "en";

type ActivityType = "buy" | "add" | "reduce" | "sell" | "hold";

type Activity = {
  type: ActivityType;
  label: string;
  percent?: number | null;
  portfolioImpactPercent?: number | null;
  positionChangePercent?: number | null;
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

const COPY = {
  zh: {
    waiting: "等待加载基金经理数据",
    refreshing: "正在刷新基金经理缓存...",
    loading: "正在加载基金经理数据...",
    loaded: "组合数据已加载",
    failed: "基金经理数据加载失败",
    unknownError: "未知错误",
    back: "超级投资者",
    fallbackDesc: "持仓结构与季度变动摘要。",
    refresh: "刷新",
    loadingButton: "加载中",
    source: "源站",
    portfolioValue: "组合市值",
    holdings: "持仓数量",
    top5Weight: "前五大占比",
    latestActivity: "最新变动",
    cachedAt: "缓存时间",
    top1: "第一大",
    buy: "新买入",
    add: "加仓",
    reduce: "减仓",
    sell: "清仓",
    topHoldings: "前十大持仓",
    topHoldingsHint: "按已披露 13F 组合仓位占比排序",
    quarterlyActivity: "季度变动",
    latestQuarter: "最新季度",
    noItems: "暂无项目",
    fullHoldings: "完整持仓",
    rows: "行",
    stock: "股票",
    weight: "仓位",
    activity: "动作",
    shares: "股数",
    value: "市值",
    hold: "持有",
    disclaimer: "DATAROMA 内容在这里仅作为小范围研究摘要展示，并保留源站链接。13F 披露存在滞后，本页不构成投资建议。",
    langLabel: "语言",
    routeLoading: "正在加载基金经理页面...",
  },
  en: {
    waiting: "Waiting for manager data",
    refreshing: "Refreshing manager cache...",
    loading: "Loading manager data...",
    loaded: "Manager data loaded",
    failed: "Manager data failed to load",
    unknownError: "Unknown error",
    back: "Superinvestors",
    fallbackDesc: "Portfolio holdings and quarterly activity summary.",
    refresh: "Refresh",
    loadingButton: "Loading",
    source: "Source",
    portfolioValue: "Portfolio value",
    holdings: "Holdings",
    top5Weight: "Top 5 weight",
    latestActivity: "Latest activity",
    cachedAt: "Cached at",
    top1: "Top 1",
    buy: "Buy",
    add: "Add",
    reduce: "Reduce",
    sell: "Sell",
    topHoldings: "Top Holdings",
    topHoldingsHint: "Position weight in reported 13F portfolio",
    quarterlyActivity: "Quarterly Activity",
    latestQuarter: "Latest quarter",
    noItems: "No items",
    fullHoldings: "Full Holdings",
    rows: "rows",
    stock: "Stock",
    weight: "Weight",
    activity: "Activity",
    shares: "Shares",
    value: "Value",
    hold: "Hold",
    disclaimer: "DATAROMA content is shown as a small research summary with source links. 13F filings are delayed and this page is not investment advice.",
    langLabel: "Language",
    routeLoading: "Loading manager route...",
  },
} satisfies Record<Locale, Record<string, string>>;

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

function translateActivity(activity: Activity, locale: Locale) {
  if (!activity.label) return COPY[locale].hold;
  const displayPercent = activity.portfolioImpactPercent ?? activity.percent;
  const percent = displayPercent === undefined || displayPercent === null ? "" : ` ${formatNumber(displayPercent)}%`;
  if (locale === "en") {
    if (activity.type === "buy") return `${COPY.en.buy}${percent}`;
    if (activity.type === "add") return `${COPY.en.add}${percent}`;
    if (activity.type === "reduce") return `${COPY.en.reduce}${percent}`;
    if (activity.type === "sell") return `${COPY.en.sell}${percent}`;
    return COPY.en.hold;
  }
  if (activity.type === "buy") return `${COPY.zh.buy}${percent}`;
  if (activity.type === "add") return `${COPY.zh.add}${percent}`;
  if (activity.type === "reduce") return `${COPY.zh.reduce}${percent}`;
  if (activity.type === "sell") return `${COPY.zh.sell}${percent}`;
  return COPY.zh.hold;
}

function activityWithPortfolioImpact(item: ActivityItem) {
  if (item.portfolioImpactPercent === undefined || item.portfolioImpactPercent === null) return item.activity;
  return {
    ...item.activity,
    portfolioImpactPercent: item.portfolioImpactPercent,
    label: item.activity.type === "buy" ? `Buy ${formatNumber(item.portfolioImpactPercent)}%` : item.activity.label,
  };
}

function ActivityBadge({ activity, locale }: { activity: Activity; locale: Locale }) {
  return <span className={`activity-badge ${actionTone(activity.type)}`}>{translateActivity(activity, locale)}</span>;
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
  const [locale, setLocale] = useState<Locale>("zh");
  const copy = COPY[locale];
  const [data, setData] = useState<ManagerPayload | null>(null);
  const [statusKey, setStatusKey] = useState<"waiting" | "refreshing" | "loading" | "loaded" | "failed">("waiting");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function loadData(refresh = false) {
    setIsLoading(true);
    setError(null);
    setStatusKey(refresh ? "refreshing" : "loading");
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
            {copy.back}
          </Link>
          <span className="eyebrow-label">DATAROMA / MANAGER</span>
          <h1>{data?.manager || managerCode}</h1>
          <p>{data?.firm || copy.fallbackDesc}</p>
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
          <a href={data?.sourceUrl || `https://www.dataroma.com/m/holdings.php?m=${managerCode}`} target="_blank" rel="noreferrer">
            {copy.source}
          </a>
        </div>
      </section>

      <section className="manager-summary-grid">
        <SummaryMetric label={copy.portfolioValue} value={formatMoney(data?.portfolioValue)} detail={data?.period || undefined} />
        <SummaryMetric label={copy.holdings} value={formatNumber(data?.reportedStockCount ?? data?.concentration.holdingCount, 0)} detail={data?.portfolioDate || undefined} />
        <SummaryMetric label={copy.top5Weight} value={`${formatNumber(data?.concentration.top5Percent)}%`} detail={`${copy.top1}: ${formatNumber(data?.concentration.top1Percent)}%`} />
        <SummaryMetric label={copy.latestActivity} value={`${data?.latestActivitySummary.buy ?? 0} ${copy.buy} / ${data?.latestActivitySummary.add ?? 0} ${copy.add}`} detail={`${data?.latestActivitySummary.reduce ?? 0} ${copy.reduce} / ${data?.latestActivitySummary.sell ?? 0} ${copy.sell}`} />
        <SummaryMetric label={copy.cachedAt} value={fetchedAt} detail={data?.period && statusKey === "loaded" ? `${data.period} ${copy.loaded}` : copy[statusKey]} />
      </section>

      {error ? <div className="error-box">{error}</div> : null}

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>{copy.topHoldings}</h2>
          <span>{copy.topHoldingsHint}</span>
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
          <h2>{copy.quarterlyActivity}</h2>
          <span>{data?.activityByQuarter[0]?.quarter || copy.latestQuarter}</span>
        </div>
        <div className="activity-group-grid">
          {(["buy", "add", "reduce", "sell"] as const).map((type) => (
            <article key={type} className={`activity-group ${actionTone(type)}`}>
              <h3>{copy[type]}</h3>
              {groupedActivity[type].length ? (
                groupedActivity[type].slice(0, 8).map((item) => (
                  <div key={`${type}-${item.ticker}`} className="activity-item-row">
                    <strong>{item.ticker}</strong>
                    <span>{item.name}</span>
                    <em>{translateActivity(activityWithPortfolioImpact(item), locale)}</em>
                  </div>
                ))
              ) : (
                <p>{copy.noItems}</p>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="dataroma-panel">
        <div className="dataroma-panel-header">
          <h2>{copy.fullHoldings}</h2>
          <span>{data?.holdings.length ?? 0} {copy.rows}</span>
        </div>
        <div className="manager-holdings-table">
          <div className="manager-holdings-head">
            <span>{copy.stock}</span>
            <span>{copy.weight}</span>
            <span>{copy.activity}</span>
            <span>{copy.shares}</span>
            <span>{copy.value}</span>
          </div>
          {(data?.holdings ?? []).map((item) => (
            <div key={`holding-${item.ticker}`} className="manager-holdings-row">
              <span>
                <strong>{item.ticker}</strong>
                <em>{item.name}</em>
              </span>
              <span>{formatNumber(item.portfolioPercent)}%</span>
              <span>
                <ActivityBadge activity={item.recentActivity} locale={locale} />
              </span>
              <span>{formatShares(item.shares)}</span>
              <span>{formatMoney(item.value)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="dataroma-disclaimer">
        {copy.disclaimer}
      </section>
    </AppShell>
  );
}

export default function ManagerDetailClient() {
  return (
    <Suspense fallback={<div className="status-line">{COPY.zh.routeLoading}</div>}>
      <ManagerDetailContent />
    </Suspense>
  );
}
