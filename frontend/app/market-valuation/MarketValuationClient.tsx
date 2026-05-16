"use client";

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { AppShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

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
    valuationZone: "cheap" | "fair" | "expensive" | "extreme";
    earningsYield: number;
    tenYearYield?: { date: string; value: number; unit: string; source: string } | null;
    equityRiskPremium?: number | null;
    years: number;
  };
  peLine: Array<{ date: string; pe: number }>;
  priceLine: Array<{ date: string; value: number }>;
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

function getValuationZoneLabel(zone?: MarketIndexValuationResponse["summary"]["valuationZone"]) {
  if (zone === "cheap") return "偏低";
  if (zone === "fair") return "合理";
  if (zone === "expensive") return "偏贵";
  if (zone === "extreme") return "极贵";
  return "-";
}

function getValuationZoneTone(zone?: MarketIndexValuationResponse["summary"]["valuationZone"]) {
  if (zone === "cheap") return "positive";
  if (zone === "fair") return "neutral";
  if (zone === "expensive") return "warning";
  if (zone === "extreme") return "danger";
  return "neutral";
}

function getDataQualityLabel(value?: string) {
  if (value === "available") return "已连接";
  if (value === "not_used") return "本页未使用";
  if (value === "not_connected") return "未连接";
  return value || "-";
}

export default function MarketValuationClient() {
  const [marketIndexCode, setMarketIndexCode] = useState("sp500");
  const [marketIndexYears, setMarketIndexYears] = useState("20");
  const [marketIndexData, setMarketIndexData] = useState<MarketIndexValuationResponse | null>(null);
  const [marketIndexStatus, setMarketIndexStatus] = useState("等待加载大盘估值数据");
  const [marketIndexError, setMarketIndexError] = useState<string | null>(null);
  const [isMarketIndexLoading, setIsMarketIndexLoading] = useState(false);
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  async function loadMarketIndexData(indexCode = marketIndexCode, rangeYears = marketIndexYears, refresh = false) {
    if (isMarketIndexLoading) return;
    setIsMarketIndexLoading(true);
    setMarketIndexStatus("正在加载大盘估值数据...");
    setMarketIndexError(null);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const params = new URLSearchParams({ index: indexCode, years: rangeYears });
      if (refresh) params.set("refresh", "1");
      const response = await fetch(`${API_BASE}/api/market-index-valuation?${params.toString()}`, {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as MarketIndexValuationResponse;
      setMarketIndexData(data);
      setMarketIndexStatus(data.status === "stale_cache" ? "已使用最近缓存数据" : "大盘估值数据已加载");
    } catch (error) {
      const message = error instanceof DOMException && error.name === "AbortError" ? "请求超时，请确认后端服务是否启动" : error instanceof Error ? error.message : "未知错误";
      setMarketIndexError(message);
      setMarketIndexStatus("大盘估值数据加载失败");
    } finally {
      window.clearTimeout(timeout);
      setIsMarketIndexLoading(false);
    }
  }

  useEffect(() => {
    void loadMarketIndexData("sp500", "20");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleResize = () => chart.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!marketIndexData || !chartRef.current) return;
    chart.current = echarts.getInstanceByDom(chartRef.current) ?? echarts.init(chartRef.current);

    const dates = marketIndexData.peLine.map((item) => item.date);
    const horizontalLine = (value: number) => dates.map((date) => [date, value]);

    chart.current.clear();
    chart.current.setOption(
      {
        animationDuration: 400,
        tooltip: {
          trigger: "axis",
          valueFormatter: (value: number | string) => {
            if (typeof value !== "number") return `${value}`;
            return Number.isFinite(value) ? `${value.toFixed(2)}x` : "-";
          },
        },
        legend: { top: 8, data: ["PE", "均值", "低估线", "高估线"] },
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

  return (
    <AppShell active="markets">
      <section className="market-valuation-section market-valuation-page" aria-label="大盘估值">
        <div className="market-valuation-header">
          <div>
            <div className="summary-kicker">Market Valuation</div>
            <h1>大盘估值仪表盘</h1>
            <p>{marketIndexData?.conclusion || "查看标普500、纳斯达克100等指数当前 PE 与历史区间的位置。"}</p>
          </div>
          <div className="market-index-controls">
            {[
              { code: "sp500", label: "标普500" },
              { code: "nasdaq100", label: "纳斯达克100" },
              { code: "csi300", label: "沪深300" },
              { code: "csi500", label: "中证500" },
              { code: "dividend_low_vol_100", label: "红利低波100" },
            ].map((item) => (
              <button
                key={item.code}
                type="button"
                className={`market-index-button ${marketIndexCode === item.code ? "active" : ""}`}
                onClick={() => {
                  setMarketIndexCode(item.code);
                  void loadMarketIndexData(item.code, marketIndexYears);
                }}
              >
                {item.label}
              </button>
            ))}
            <select
              value={marketIndexYears}
              onChange={(event) => {
                setMarketIndexYears(event.target.value);
                void loadMarketIndexData(marketIndexCode, event.target.value);
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
              disabled={isMarketIndexLoading}
              onClick={() => void loadMarketIndexData(marketIndexCode, marketIndexYears, true)}
            >
              {isMarketIndexLoading ? "加载中" : "刷新"}
            </button>
          </div>
        </div>

        {marketIndexError ? <div className="error-box">大盘估值加载失败：{marketIndexError}</div> : null}

        {marketIndexData ? (
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
                <span>盈利收益率 / 10Y</span>
                <strong>
                  {formatNumber(marketIndexData.summary.earningsYield)}% /{" "}
                  {formatNumber(marketIndexData.summary.tenYearYield?.value)}%
                </strong>
                <em>风险溢价 {formatNumber(marketIndexData.summary.equityRiskPremium)}%</em>
              </div>
            </div>

            <div className="market-valuation-body">
              <div className="market-chart-card">
                <div className="market-chart-title">历史 PE 趋势</div>
                <div ref={chartRef} className="chart-box market-index-chart" />
              </div>
              <div className="market-side-card">
                <div className="market-chart-title">数据口径</div>
                <div className="market-source-row">
                  <span>PE 历史</span>
                  <strong>{getDataQualityLabel(marketIndexData.dataQuality.peHistory)}</strong>
                </div>
                <div className="market-source-row">
                  <span>价格/EPS拆解</span>
                  <strong>{getDataQualityLabel(marketIndexData.dataQuality.eps)}</strong>
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
        ) : (
          <div className="market-empty-state">{marketIndexStatus}</div>
        )}
      </section>
    </AppShell>
  );
}
