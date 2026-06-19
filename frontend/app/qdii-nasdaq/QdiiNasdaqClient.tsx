"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

type SubscribeStatus = "open" | "limited" | "paused";
type FundMarket = "SH" | "SZ" | "OTC";

type QdiiFund = {
  fundCode: string;
  fundName: string;
  managerName: string;
  market: FundMarket;
  fundType: string;
  trackingIndex: string;
  subscribeStatus: SubscribeStatus;
  redeemStatus: string;
  dailyLimitAmount?: number | null;
  singleLimitAmount?: number | null;
  creationUnit?: number | null;
  latestScaleYi?: number | null;
  latestNav?: number | null;
  navDate?: string | null;
  subscribeStatusRaw?: string;
  sourceStatus: string;
  sourceNote: string;
};

type QdiiPayload = {
  status: string;
  theme: string;
  asOf: string;
  summary: {
    totalCount: number;
    nasdaq100Count?: number;
    managerCount: number;
    etfCount: number;
    otcCount: number;
    availableCount: number;
    openCount: number;
    limitedCount: number;
    pausedCount: number;
    totalScaleYi: number;
  };
  funds: QdiiFund[];
  sourcePlan: Array<{ name: string; coverage: string; integration: string }>;
  dataGaps: string[];
};

function formatAmount(value?: number | null, status?: SubscribeStatus) {
  if (value === undefined || value === null) return "不限额";
  if (value <= 0) return status === "paused" ? "不可申购" : "额度见渠道";
  if (value >= 10000) return `${(value / 10000).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 万元`;
  return `${value.toLocaleString("zh-CN")} 元`;
}

function formatNumber(value?: number | null, digits = 1) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function getStatusLabel(status: SubscribeStatus) {
  if (status === "open") return "可申购";
  if (status === "limited") return "限额申购";
  return "暂停申购";
}

function getMarketLabel(market: FundMarket) {
  if (market === "SH") return "上交所";
  if (market === "SZ") return "深交所";
  return "场外";
}

export default function QdiiNasdaqClient() {
  const [data, setData] = useState<QdiiPayload | null>(null);
  const [status, setStatus] = useState("等待加载 QDII 纳指基金数据");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [marketFilter, setMarketFilter] = useState<"all" | FundMarket>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | SubscribeStatus>("all");
  const [keyword, setKeyword] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  async function loadData(refresh = false) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 18000);
    setIsLoading(true);
    setStatus("正在加载 QDII 纳指基金数据...");
    setError(null);

    try {
      const params = new URLSearchParams();
      if (refresh) params.set("refresh", "1");
      const url = `${API_BASE}/api/qdii-nasdaq-funds${params.size ? `?${params.toString()}` : ""}`;
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const body = (await response.json()) as { error?: string };
          if (body.error) message = body.error;
        } catch {
          // Keep the status code when the backend returns a plain error.
        }
        throw new Error(message);
      }
      const payload = (await response.json()) as QdiiPayload;
      setData(payload);
      setStatus(payload.status === "live" ? "已加载今日实时源缓存" : "QDII 纳指基金数据已加载");
    } catch (loadError) {
      const message =
        loadError instanceof DOMException && loadError.name === "AbortError"
          ? "请求超时，请确认后端服务是否启动"
          : loadError instanceof Error
            ? loadError.message
            : "未知错误";
      setError(message);
      setStatus("QDII 纳指基金数据加载失败");
    } finally {
      window.clearTimeout(timeout);
      setIsLoading(false);
      abortRef.current = null;
    }
  }

  useEffect(() => {
    void loadData();
    return () => abortRef.current?.abort();
  }, []);

  const filteredFunds = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return (data?.funds ?? []).filter((fund) => {
      if (marketFilter !== "all" && fund.market !== marketFilter) return false;
      if (statusFilter !== "all" && fund.subscribeStatus !== statusFilter) return false;
      if (!normalizedKeyword) return true;
      const haystack = `${fund.fundCode} ${fund.fundName} ${fund.managerName} ${fund.trackingIndex}`.toLowerCase();
      return haystack.includes(normalizedKeyword);
    });
  }, [data?.funds, keyword, marketFilter, statusFilter]);

  return (
    <AppShell active="qdii">
      <section className="qdii-page" aria-label="QDII 纳指基金">
        <div className="qdii-hero">
          <div>
            <div className="summary-kicker">QDII Nasdaq Funds</div>
            <h1>QDII 纳指基金申购看板</h1>
            <p>
              跟踪国内纳斯达克主题 QDII 基金的基金公司、场内/场外类型、申购状态、限额和 ETF 最小申赎单位。
            </p>
          </div>
          <div className="qdii-actions">
            <button type="button" onClick={() => void loadData(true)} disabled={isLoading}>
              {isLoading ? "加载中" : "刷新数据"}
            </button>
          </div>
        </div>

        {error ? <div className="error-box">QDII 数据加载失败：{error}</div> : null}

        <div className="qdii-status-line">
          <strong>{status}</strong>
          {data?.asOf ? <span>数据批次：{new Date(data.asOf).toLocaleString("zh-CN")}</span> : null}
        </div>

        {data ? (
          <>
            <div className="qdii-kpi-grid">
              <article>
                <span>基金数量</span>
                <strong>{data.summary.totalCount}</strong>
                <em>纳指100 {data.summary.nasdaq100Count ?? "-"} / ETF {data.summary.etfCount}</em>
              </article>
              <article>
                <span>基金公司</span>
                <strong>{data.summary.managerCount}</strong>
                <em>按管理人去重</em>
              </article>
              <article className="tone-positive">
                <span>可申购 / 总数</span>
                <strong>
                  {data.summary.availableCount}/{data.summary.totalCount}
                </strong>
                <em>含限额申购</em>
              </article>
              <article className="tone-warning">
                <span>限额 / 暂停</span>
                <strong>
                  {data.summary.limitedCount}/{data.summary.pausedCount}
                </strong>
                <em>需每日公告覆盖</em>
              </article>
              <article>
                <span>总规模</span>
                <strong>{data.summary.totalScaleYi ? `${formatNumber(data.summary.totalScaleYi)} 亿` : "待接入"}</strong>
                <em>需接交易所/数据商规模</em>
              </article>
            </div>

            <div className="qdii-filter-bar">
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索代码、基金公司、简称"
              />
              <select value={marketFilter} onChange={(event) => setMarketFilter(event.target.value as "all" | FundMarket)}>
                <option value="all">全部市场</option>
                <option value="SH">上交所</option>
                <option value="SZ">深交所</option>
                <option value="OTC">场外</option>
              </select>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as "all" | SubscribeStatus)}
              >
                <option value="all">全部状态</option>
                <option value="open">可申购</option>
                <option value="limited">限额申购</option>
                <option value="paused">暂停申购</option>
              </select>
            </div>

            <div className="qdii-table">
              <div className="qdii-table-head">
                <span>基金</span>
                <span>基金公司</span>
                <span>市场/类型</span>
                <span>申购状态</span>
                <span>额度</span>
                <span>规模/申赎单位</span>
              </div>
              {filteredFunds.map((fund) => (
                <div className="qdii-table-row" key={fund.fundCode}>
                  <div>
                    <strong>{fund.fundName}</strong>
                    <em>
                      {fund.fundCode} · {fund.trackingIndex}
                    </em>
                  </div>
                  <div>{fund.managerName}</div>
                  <div>
                    <strong>{getMarketLabel(fund.market)}</strong>
                    <em>{fund.fundType}</em>
                  </div>
                  <div>
                    <span className={`qdii-status-badge status-${fund.subscribeStatus}`}>
                      {getStatusLabel(fund.subscribeStatus)}
                    </span>
                    <em>赎回：{fund.redeemStatus === "open" ? "开放" : fund.redeemStatus}</em>
                  </div>
                  <div>
                    <strong>{formatAmount(fund.dailyLimitAmount, fund.subscribeStatus)}</strong>
                    <em>单日/账户口径</em>
                  </div>
                  <div>
                    <strong>{fund.latestNav ? formatNumber(fund.latestNav, 4) : formatNumber(fund.latestScaleYi)}</strong>
                    <em>
                      {fund.navDate
                        ? `净值日期 ${fund.navDate}`
                        : fund.creationUnit
                          ? `申赎单位 ${fund.creationUnit.toLocaleString("zh-CN")} 份`
                          : "规模待接入"}
                    </em>
                  </div>
                </div>
              ))}
              {!filteredFunds.length ? <div className="qdii-empty">没有符合当前筛选条件的基金。</div> : null}
            </div>

            <div className="qdii-source-grid">
              {data.sourcePlan.map((item) => (
                <article key={item.name}>
                  <span>{item.name}</span>
                  <strong>{item.coverage}</strong>
                  <p>{item.integration}</p>
                </article>
              ))}
            </div>

            <div className="qdii-disclaimer">
              {data.dataGaps.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </div>
          </>
        ) : (
          <div className="market-empty-state">{status}</div>
        )}
      </section>
    </AppShell>
  );
}
