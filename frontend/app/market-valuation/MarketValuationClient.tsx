"use client";

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { AppShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

type ValuationZone = "cheap" | "fair" | "expensive" | "extreme";

type MarketIndexValuationResponse = {
  indexCode: string;
  indexName: string;
  displayName: string;
  status: string;
  sourceLabel: string;
  dataQuality: {
    peHistory: string;
    eps: string;
    interestRate: string;
    notes: string[];
  };
  summary: {
    currentDate: string;
    currentPe: number;
    meanPe: number;
    medianPe: number;
    lowLine: number;
    highLine: number;
    percentile: number;
    valuationZone: ValuationZone;
    earningsYield: number;
    tenYearYield?: { date: string; value: number; unit: string; source: string } | null;
    equityRiskPremium?: number | null;
    years: number;
  };
  peLine: Array<{ date: string; pe: number }>;
  priceLine: Array<{ date: string; value: number }>;
  interestRateLine?: Array<{ date: string; value: number }>;
  interestRateLabel?: string;
  conclusion: string;
  sourceUrls: string[];
};

type BuffettIndicatorResponse = {
  marketCode: string;
  marketName: string;
  displayName: string;
  status: string;
  currency: string;
  sourceLabel: string;
  dataQuality: {
    marketCap: string;
    gdp: string;
    notes: string[];
  };
  summary: {
    currentDate: string;
    currentRatio: number;
    meanRatio: number;
    medianRatio: number;
    lowLine: number;
    highLine: number;
    percentile: number;
    valuationZone: ValuationZone;
    years: number;
    actualYears: number;
  };
  ratioLine: Array<{ date: string; ratio: number }>;
  marketCapLine: Array<{ date: string; value: number }>;
  gdpLine: Array<{ date: string; value: number }>;
  conclusion: string;
  sourceUrls: string[];
};

function formatNumber(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatPercent(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function getValuationZoneLabel(zone?: ValuationZone) {
  if (zone === "cheap") return "偏低";
  if (zone === "fair") return "合理";
  if (zone === "expensive") return "偏贵";
  if (zone === "extreme") return "极贵";
  return "-";
}

function getValuationZoneTone(zone?: ValuationZone) {
  if (zone === "cheap") return "positive";
  if (zone === "fair") return "neutral";
  if (zone === "expensive") return "warning";
  if (zone === "extreme") return "danger";
  return "neutral";
}

function getDataQualityLabel(value?: string) {
  if (value === "available") return "已连接";
  if (value === "official") return "官方季度";
  if (value === "reported") return "已披露";
  if (value === "estimated") return "最新估算";
  if (value === "not_used") return "本页未使用";
  if (value === "not_connected") return "未连接";
  return value || "-";
}

export default function MarketValuationClient() {
  const [activeValuationType, setActiveValuationType] = useState<"index" | "buffett">("index");
  const [marketIndexCode, setMarketIndexCode] = useState("sp500");
  const [marketIndexYears, setMarketIndexYears] = useState("5");
  const [marketIndexData, setMarketIndexData] = useState<MarketIndexValuationResponse | null>(null);
  const [marketIndexStatus, setMarketIndexStatus] = useState("等待加载大盘估值数据");
  const [marketIndexError, setMarketIndexError] = useState<string | null>(null);
  const [isMarketIndexLoading, setIsMarketIndexLoading] = useState(false);
  const [buffettMarketCode, setBuffettMarketCode] = useState("us");
  const [buffettYears, setBuffettYears] = useState("5");
  const [buffettData, setBuffettData] = useState<BuffettIndicatorResponse | null>(null);
  const [buffettStatus, setBuffettStatus] = useState("等待加载巴菲特指数");
  const [buffettError, setBuffettError] = useState<string | null>(null);
  const [isBuffettLoading, setIsBuffettLoading] = useState(false);
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const rateChartRef = useRef<HTMLDivElement | null>(null);
  const rateChart = useRef<echarts.ECharts | null>(null);
  const buffettChartRef = useRef<HTMLDivElement | null>(null);
  const buffettChart = useRef<echarts.ECharts | null>(null);
  const marketIndexAbortRef = useRef<AbortController | null>(null);
  const marketIndexRequestIdRef = useRef(0);
  const marketIndexRefreshInFlightRef = useRef(false);
  const buffettAbortRef = useRef<AbortController | null>(null);
  const buffettRequestIdRef = useRef(0);
  const buffettRefreshInFlightRef = useRef(false);

  async function loadMarketIndexData(indexCode = marketIndexCode, rangeYears = marketIndexYears, refresh = false) {
    if (refresh && marketIndexRefreshInFlightRef.current) return;
    if (refresh) marketIndexRefreshInFlightRef.current = true;
    marketIndexAbortRef.current?.abort();
    const requestId = marketIndexRequestIdRef.current + 1;
    marketIndexRequestIdRef.current = requestId;
    setIsMarketIndexLoading(true);
    setMarketIndexStatus("正在加载大盘估值数据...");
    setMarketIndexError(null);
    setMarketIndexData(null);
    const controller = new AbortController();
    marketIndexAbortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      const params = new URLSearchParams({ index: indexCode, years: rangeYears });
      if (refresh) params.set("refresh", "1");
      const response = await fetch(`${API_BASE}/api/market-index-valuation?${params.toString()}`, {
        signal: controller.signal,
      });
      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        try {
          const errorData = (await response.json()) as { error?: string };
          if (errorData.error) errorMessage = errorData.error;
        } catch {
          // Keep the HTTP status when the backend returns a non-JSON error body.
        }
        throw new Error(errorMessage);
      }
      const data = (await response.json()) as MarketIndexValuationResponse;
      if (marketIndexRequestIdRef.current !== requestId) return;
      setMarketIndexData(data);
      setMarketIndexStatus(data.status === "stale_cache" ? "已使用最近缓存数据" : "大盘估值数据已加载");
    } catch (error) {
      if (marketIndexRequestIdRef.current !== requestId) return;
      const message = error instanceof DOMException && error.name === "AbortError" ? "请求超时，请确认后端服务是否启动" : error instanceof Error ? error.message : "未知错误";
      setMarketIndexError(message);
      setMarketIndexStatus("大盘估值数据加载失败");
    } finally {
      window.clearTimeout(timeout);
      if (marketIndexRequestIdRef.current === requestId) {
        marketIndexAbortRef.current = null;
        setIsMarketIndexLoading(false);
      }
      if (refresh) marketIndexRefreshInFlightRef.current = false;
    }
  }

  async function loadBuffettData(marketCode = buffettMarketCode, rangeYears = buffettYears, refresh = false) {
    if (refresh && buffettRefreshInFlightRef.current) return;
    if (refresh) buffettRefreshInFlightRef.current = true;
    buffettAbortRef.current?.abort();
    const requestId = buffettRequestIdRef.current + 1;
    buffettRequestIdRef.current = requestId;
    setIsBuffettLoading(true);
    setBuffettStatus("正在加载巴菲特指数...");
    setBuffettError(null);
    setBuffettData(null);
    const controller = new AbortController();
    buffettAbortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 25000);
    try {
      const params = new URLSearchParams({ market: marketCode, years: rangeYears });
      if (refresh) params.set("refresh", "1");
      const response = await fetch(`${API_BASE}/api/market-buffett-indicator?${params.toString()}`, {
        signal: controller.signal,
      });
      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        try {
          const errorData = (await response.json()) as { error?: string };
          if (errorData.error) errorMessage = errorData.error;
        } catch {
          // Keep the HTTP status when the backend returns a non-JSON error body.
        }
        throw new Error(errorMessage);
      }
      const data = (await response.json()) as BuffettIndicatorResponse;
      if (buffettRequestIdRef.current !== requestId) return;
      setBuffettData(data);
      setBuffettStatus(data.status === "stale_cache" ? "已使用最近缓存数据" : "巴菲特指数已加载");
    } catch (error) {
      if (buffettRequestIdRef.current !== requestId) return;
      const message = error instanceof DOMException && error.name === "AbortError" ? "请求超时，请确认后端服务是否启动" : error instanceof Error ? error.message : "未知错误";
      setBuffettError(message);
      setBuffettStatus("巴菲特指数加载失败");
    } finally {
      window.clearTimeout(timeout);
      if (buffettRequestIdRef.current === requestId) {
        buffettAbortRef.current = null;
        setIsBuffettLoading(false);
      }
      if (refresh) buffettRefreshInFlightRef.current = false;
    }
  }

  useEffect(() => {
    void loadMarketIndexData("sp500", "5");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleResize = () => {
      chart.current?.resize();
      rateChart.current?.resize();
      buffettChart.current?.resize();
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.current?.dispose();
      chart.current = null;
      rateChart.current?.dispose();
      rateChart.current = null;
      buffettChart.current?.dispose();
      buffettChart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!marketIndexData || !chartRef.current) return;
    chart.current = echarts.getInstanceByDom(chartRef.current) ?? echarts.init(chartRef.current);

    const dates = marketIndexData.peLine.map((item) => item.date);
    const horizontalLine = (value: number) => dates.map((date) => [date, value]);
    const legendData = ["PE", "均值", "低估线", "高估线"];

    chart.current.clear();
    chart.current.setOption(
      {
        animationDuration: 400,
        tooltip: {
          trigger: "axis",
          formatter: (params: unknown) => {
            const rows = (Array.isArray(params) ? params : [params]) as Array<{
              axisValueLabel?: string;
              marker?: string;
              seriesName?: string;
              value?: unknown;
            }>;
            const title = rows[0]?.axisValueLabel || "";
            const lines = rows.map((row) => {
              const rawValue = Array.isArray(row.value) ? row.value[1] : row.value;
              const numericValue = typeof rawValue === "number" ? rawValue : Number(rawValue);
              const value = Number.isFinite(numericValue) ? `${numericValue.toFixed(2)}x` : "-";
              return `${row.marker || ""}${row.seriesName || ""}: ${value}`;
            });
            return [title, ...lines].filter(Boolean).join("<br/>");
          },
        },
        legend: { top: 8, data: legendData },
        axisPointer: { link: [{ xAxisIndex: [0] }] },
        grid: { top: 58, left: 58, right: 40, bottom: 42, containLabel: true },
        xAxis: {
          type: "time",
          boundaryGap: false,
          axisLabel: {
            hideOverlap: true,
            formatter(value: number) {
              return echarts.time.format(value, "{yyyy}", false);
            },
          },
        },
        yAxis: {
          type: "value",
          name: "PE(x)",
          splitLine: { lineStyle: { color: "#dce5df" } },
        },
        series: [
          {
            name: "PE",
            type: "line",
            showSymbol: false,
            smooth: true,
            data: marketIndexData.peLine.map((item) => [item.date, item.pe]),
            lineStyle: { width: 3, color: "#101820" },
            itemStyle: { color: "#101820" },
          },
          {
            name: "均值",
            type: "line",
            showSymbol: false,
            data: horizontalLine(marketIndexData.summary.meanPe),
            lineStyle: { type: "dashed", width: 2, color: "#b7791f" },
          },
          {
            name: "低估线",
            type: "line",
            showSymbol: false,
            data: horizontalLine(marketIndexData.summary.lowLine),
            lineStyle: { type: "dashed", width: 2, color: "#087f5b" },
          },
          {
            name: "高估线",
            type: "line",
            showSymbol: false,
            data: horizontalLine(marketIndexData.summary.highLine),
            lineStyle: { type: "dashed", width: 2, color: "#d93025" },
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => {
      chart.current?.resize();
      window.setTimeout(() => chart.current?.resize(), 80);
    });
  }, [marketIndexData]);

  useEffect(() => {
    const interestRateLine = marketIndexData?.interestRateLine ?? [];
    if (!marketIndexData || !rateChartRef.current || !interestRateLine.length) {
      rateChart.current?.dispose();
      rateChart.current = null;
      return;
    }

    const interestRateLabel = marketIndexData.interestRateLabel || "10Y";
    rateChart.current = echarts.getInstanceByDom(rateChartRef.current) ?? echarts.init(rateChartRef.current);
    rateChart.current.clear();
    rateChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: {
          trigger: "axis",
          valueFormatter: (value: number | string) => {
            const numericValue = typeof value === "number" ? value : Number(value);
            return Number.isFinite(numericValue) ? `${numericValue.toFixed(2)}%` : "-";
          },
        },
        legend: { top: 8, data: [interestRateLabel] },
        grid: { top: 48, left: 58, right: 40, bottom: 36, containLabel: true },
        xAxis: {
          type: "time",
          boundaryGap: false,
          axisLabel: {
            hideOverlap: true,
            formatter(value: number) {
              return echarts.time.format(value, "{yyyy}", false);
            },
          },
        },
        yAxis: {
          type: "value",
          name: `${interestRateLabel}(%)`,
          min: "dataMin",
          max: "dataMax",
          splitNumber: 4,
          axisLabel: { formatter: "{value}%" },
          splitLine: { lineStyle: { color: "#e5e7eb" } },
        },
        series: [
          {
            name: interestRateLabel,
            type: "line",
            showSymbol: false,
            smooth: true,
            data: interestRateLine.map((item) => [item.date, item.value]),
            lineStyle: { width: 2, color: "#2563eb" },
            itemStyle: { color: "#2563eb" },
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => {
      rateChart.current?.resize();
      window.setTimeout(() => rateChart.current?.resize(), 80);
    });
  }, [marketIndexData]);

  useEffect(() => {
    if (!buffettData || !buffettChartRef.current) return;
    buffettChart.current = echarts.getInstanceByDom(buffettChartRef.current) ?? echarts.init(buffettChartRef.current);

    const dates = buffettData.ratioLine.map((item) => item.date);
    const horizontalLine = (value: number) => dates.map((date) => [date, value]);
    const legendData = ["巴菲特指数", "均值", "低估线", "高估线"];

    buffettChart.current.clear();
    buffettChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: {
          trigger: "axis",
          formatter: (params: unknown) => {
            const rows = (Array.isArray(params) ? params : [params]) as Array<{
              axisValueLabel?: string;
              marker?: string;
              seriesName?: string;
              value?: unknown;
            }>;
            const title = rows[0]?.axisValueLabel || "";
            const lines = rows.map((row) => {
              const rawValue = Array.isArray(row.value) ? row.value[1] : row.value;
              const numericValue = typeof rawValue === "number" ? rawValue : Number(rawValue);
              const value = Number.isFinite(numericValue) ? `${numericValue.toFixed(1)}%` : "-";
              return `${row.marker || ""}${row.seriesName || ""}: ${value}`;
            });
            return [title, ...lines].filter(Boolean).join("<br/>");
          },
        },
        legend: { top: 8, data: legendData },
        grid: { top: 58, left: 58, right: 40, bottom: 42, containLabel: true },
        xAxis: {
          type: "time",
          boundaryGap: false,
          axisLabel: {
            hideOverlap: true,
            formatter(value: number) {
              return echarts.time.format(value, "{yyyy}", false);
            },
          },
        },
        yAxis: {
          type: "value",
          name: "市值/GDP(%)",
          splitLine: { lineStyle: { color: "#dce5df" } },
          axisLabel: { formatter: "{value}%" },
        },
        series: [
          {
            name: "巴菲特指数",
            type: "line",
            showSymbol: false,
            smooth: true,
            data: buffettData.ratioLine.map((item) => [item.date, item.ratio]),
            lineStyle: { width: 3, color: "#101820" },
            itemStyle: { color: "#101820" },
          },
          {
            name: "均值",
            type: "line",
            showSymbol: false,
            data: horizontalLine(buffettData.summary.meanRatio),
            lineStyle: { type: "dashed", width: 2, color: "#b7791f" },
          },
          {
            name: "低估线",
            type: "line",
            showSymbol: false,
            data: horizontalLine(buffettData.summary.lowLine),
            lineStyle: { type: "dashed", width: 2, color: "#087f5b" },
          },
          {
            name: "高估线",
            type: "line",
            showSymbol: false,
            data: horizontalLine(buffettData.summary.highLine),
            lineStyle: { type: "dashed", width: 2, color: "#d93025" },
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => {
      buffettChart.current?.resize();
      window.setTimeout(() => buffettChart.current?.resize(), 80);
    });
  }, [buffettData]);

  const isBuffettActive = activeValuationType === "buffett";
  const activeYears = isBuffettActive ? buffettYears : marketIndexYears;
  const isActiveLoading = isBuffettActive ? isBuffettLoading : isMarketIndexLoading;
  const activeError = isBuffettActive ? buffettError : marketIndexError;
  const activeStatus = isBuffettActive ? buffettStatus : marketIndexStatus;
  const activeConclusion = isBuffettActive
    ? buffettData?.conclusion || "用股票市场总市值与名义 GDP 的比例，观察美国、香港和中国内地市场的宏观估值温度。"
    : marketIndexData?.conclusion || "查看标普500、纳斯达克100等指数当前 PE 与历史区间的位置。";

  return (
    <AppShell active="markets">
      <section className="market-valuation-section market-valuation-page" aria-label="大盘估值">
        <div className="market-valuation-header">
          <div>
            <div className="summary-kicker">Market Valuation</div>
            <h1>大盘估值仪表盘</h1>
            <p>{activeConclusion}</p>
          </div>
          <div className="market-index-controls">
            {[
              { type: "index", code: "sp500", label: "标普500" },
              { type: "index", code: "nasdaq100", label: "纳斯达克100" },
              { type: "index", code: "csi300", label: "沪深300" },
              { type: "index", code: "csi500", label: "中证500" },
              { type: "index", code: "dividend_low_vol_100", label: "红利低波100" },
              { type: "buffett", code: "us", label: "美国市值/GDP" },
              { type: "buffett", code: "hk", label: "香港市值/GDP" },
              { type: "buffett", code: "cn", label: "中国市值/GDP" },
            ].map((item) => (
              <button
                key={`${item.type}-${item.code}`}
                type="button"
                className={`market-index-button ${
                  (item.type === "index" && !isBuffettActive && marketIndexCode === item.code) ||
                  (item.type === "buffett" && isBuffettActive && buffettMarketCode === item.code)
                    ? "active"
                    : ""
                }`}
                disabled={isActiveLoading}
                onClick={() => {
                  if (item.type === "buffett") {
                    setActiveValuationType("buffett");
                    setBuffettMarketCode(item.code);
                    void loadBuffettData(item.code, buffettYears);
                  } else {
                    setActiveValuationType("index");
                    setMarketIndexCode(item.code);
                    void loadMarketIndexData(item.code, marketIndexYears);
                  }
                }}
              >
                {item.label}
              </button>
            ))}
            <select
              value={activeYears}
              disabled={isActiveLoading}
              onChange={(event) => {
                if (isBuffettActive) {
                  setBuffettYears(event.target.value);
                  void loadBuffettData(buffettMarketCode, event.target.value);
                } else {
                  setMarketIndexYears(event.target.value);
                  void loadMarketIndexData(marketIndexCode, event.target.value);
                }
              }}
            >
              <option value="5">5Y</option>
              <option value="10">10Y</option>
              <option value="20">20Y</option>
              <option value="50">Max</option>
            </select>
            <button
              type="button"
              className="market-index-button"
              disabled={isActiveLoading}
              onClick={() => {
                if (isBuffettActive) {
                  void loadBuffettData(buffettMarketCode, buffettYears, true);
                } else {
                  void loadMarketIndexData(marketIndexCode, marketIndexYears, true);
                }
              }}
            >
              {isActiveLoading ? "加载中" : "刷新"}
            </button>
          </div>
        </div>

        {activeError ? <div className="error-box">大盘估值加载失败：{activeError}</div> : null}

        {!isBuffettActive && marketIndexData ? (
          <>
            <div className="market-valuation-grid">
              <div className="market-kpi-card">
                <span>当前 PE</span>
                <strong>{formatNumber(marketIndexData.summary.currentPe)}x</strong>
                <em>{marketIndexData.summary.currentDate}</em>
              </div>
              <div className={`market-kpi-card tone-${getValuationZoneTone(marketIndexData.summary.valuationZone)}`}>
                <span>历史分位</span>
                <strong>{formatPercent(marketIndexData.summary.percentile)}</strong>
                <em>{getValuationZoneLabel(marketIndexData.summary.valuationZone)}</em>
              </div>
              <div className="market-kpi-card">
                <span>均值 / 中位数</span>
                <strong>
                  {formatNumber(marketIndexData.summary.meanPe)}x / {formatNumber(marketIndexData.summary.medianPe)}x
                </strong>
                <em>近 {marketIndexData.summary.years} 年</em>
              </div>
              <div className="market-kpi-card">
                <span>历史年化回报 / 10Y</span>
                <strong>
                  {formatNumber(marketIndexData.summary.earningsYield)}% /{" "}
                  {formatNumber(marketIndexData.summary.tenYearYield?.value)}%
                </strong>
                <em>风险溢价 {formatNumber(marketIndexData.summary.equityRiskPremium)}%</em>
              </div>
            </div>

            <div className="market-valuation-body">
              <div className="market-chart-card market-comparison-card">
                  <div className="market-chart-title">历史 PE 趋势</div>
                  <div ref={chartRef} className="chart-box market-index-chart" />
                {(marketIndexData.interestRateLine ?? []).length ? (
                  <div className="market-rate-panel">
                    <div className="market-chart-title">{marketIndexData.interestRateLabel || "10Y"} 利率趋势</div>
                    <div ref={rateChartRef} className="chart-box market-rate-chart" />
                  </div>
                ) : null}
              </div>
              <div className="market-side-card">
                <div className="market-chart-title">数据口径</div>
                <div className="market-source-row">
                  <span>PE 历史</span>
                  <strong>{getDataQualityLabel(marketIndexData.dataQuality.peHistory)}</strong>
                </div>
                <div className="market-source-row">
                  <span>指数点位历史</span>
                  <strong>{marketIndexData.priceLine.length ? "已连接" : "未连接"}</strong>
                </div>
                <div className="market-source-row">
                  <span>利率</span>
                  <strong>{getDataQualityLabel(marketIndexData.dataQuality.interestRate)}</strong>
                </div>
                <p>来源：{marketIndexData.sourceLabel}</p>
                {marketIndexData.dataQuality.notes.filter(Boolean).map((note) => (
                  <p key={note}>{note}</p>
                ))}
                {marketIndexData.sourceUrls.length ? (
                  <div className="market-source-links">
                    {marketIndexData.sourceUrls.map((url) => (
                      <a key={url} href={url} target="_blank" rel="noreferrer">
                        数据源
                      </a>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          </>
        ) : isBuffettActive && buffettData ? (
          <>
            <div className="market-valuation-grid">
              <div className="market-kpi-card">
                <span>当前市值 / GDP</span>
                <strong>{formatNumber(buffettData.summary.currentRatio, 1)}%</strong>
                <em>{buffettData.summary.currentDate}</em>
              </div>
              <div className={`market-kpi-card tone-${getValuationZoneTone(buffettData.summary.valuationZone)}`}>
                <span>历史分位</span>
                <strong>{formatPercent(buffettData.summary.percentile)}</strong>
                <em>{getValuationZoneLabel(buffettData.summary.valuationZone)}</em>
              </div>
              <div className="market-kpi-card">
                <span>均值 / 中位数</span>
                <strong>
                  {formatNumber(buffettData.summary.meanRatio, 1)}% / {formatNumber(buffettData.summary.medianRatio, 1)}%
                </strong>
                <em>样本约 {formatNumber(buffettData.summary.actualYears, 1)} 年</em>
              </div>
              <div className="market-kpi-card">
                <span>区间线</span>
                <strong>
                  {formatNumber(buffettData.summary.lowLine, 1)}% / {formatNumber(buffettData.summary.highLine, 1)}%
                </strong>
                <em>20% / 80% 分位</em>
              </div>
            </div>

            <div className="market-valuation-body">
              <div className="market-chart-card market-comparison-card">
                <div className="market-chart-title">市值 / GDP 趋势</div>
                <div ref={buffettChartRef} className="chart-box market-index-chart" />
              </div>
              <div className="market-side-card">
                <div className="market-chart-title">数据口径</div>
                <div className="market-source-row">
                  <span>股票总市值</span>
                  <strong>{getDataQualityLabel(buffettData.dataQuality.marketCap)}</strong>
                </div>
                <div className="market-source-row">
                  <span>名义 GDP</span>
                  <strong>{getDataQualityLabel(buffettData.dataQuality.gdp)}</strong>
                </div>
                <div className="market-source-row">
                  <span>币种</span>
                  <strong>{buffettData.currency}</strong>
                </div>
                <p>来源：{buffettData.sourceLabel}</p>
                {buffettData.dataQuality.notes.filter(Boolean).map((note) => (
                  <p key={note}>{note}</p>
                ))}
                {buffettData.sourceUrls.length ? (
                  <div className="market-source-links">
                    {buffettData.sourceUrls.map((url) => (
                      <a key={url} href={url} target="_blank" rel="noreferrer">
                        数据源
                      </a>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          </>
        ) : (
          <div className="market-empty-state">{activeStatus}</div>
        )}
      </section>
    </AppShell>
  );
}
