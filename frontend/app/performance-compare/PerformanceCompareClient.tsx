"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import { AppShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");
const MAX_COMPANIES = 8;

type MetricId =
  | "revenue"
  | "netProfit"
  | "deductedNetProfit"
  | "grossMargin"
  | "netMargin"
  | "roe"
  | "operatingCashFlow"
  | "debtRatio"
  | "eps";
type ChartMode = "sameAxis" | "dualAxis" | "indexed";
type TimeRange = "5" | "10";

type Company = {
  code: string;
  name: string;
};

type MetricPoint = {
  date: string;
  value: number | null;
};

type CompanySeries = Company & {
  points: MetricPoint[];
  status: "idle" | "loading" | "loaded" | "error";
  error?: string;
};

type RevenueResponse = {
  revenueBars?: MetricPoint[];
};

type ProfitResponse = {
  profitBars?: MetricPoint[];
};

type CashFlowResponse = {
  operatingCashFlow?: MetricPoint[];
};

type MetricConfig = {
  id: MetricId;
  label: string;
  unit: string;
  description: string;
  enabled: boolean;
  dataGap?: string;
  load?: (stock: string, years: TimeRange) => Promise<MetricPoint[]>;
};

const COMPANIES: Company[] = [
  { code: "600519", name: "贵州茅台" },
  { code: "000858", name: "五粮液" },
  { code: "300750", name: "宁德时代" },
  { code: "002594", name: "比亚迪" },
  { code: "000333", name: "美的集团" },
  { code: "601318", name: "中国平安" },
  { code: "600036", name: "招商银行" },
  { code: "601899", name: "紫金矿业" },
  { code: "600309", name: "万华化学" },
  { code: "002475", name: "立讯精密" },
];

async function fetchJson<T>(url: string, fallbackMessage: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`${fallbackMessage}：后端没有返回 JSON`);
  }
  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "detail" in payload ? String((payload as { detail: unknown }).detail) : text;
    throw new Error(message || fallbackMessage);
  }
  return payload as T;
}

function normalizePoints(points: MetricPoint[] | undefined, years: TimeRange) {
  const yearCount = Number(years);
  return (points ?? [])
    .filter((item) => item.date && item.value !== undefined)
    .map((item) => ({
      date: item.date.slice(0, 4),
      value: typeof item.value === "number" && Number.isFinite(item.value) ? item.value : null,
    }))
    .filter((item, index, rows) => rows.findIndex((row) => row.date === item.date) === index)
    .slice(-yearCount);
}

const METRICS: MetricConfig[] = [
  {
    id: "revenue",
    label: "营业收入",
    unit: "亿元",
    description: "同一口径查看收入规模变化",
    enabled: true,
    load: async (stock, years) => {
      const params = new URLSearchParams({ stock, years });
      const data = await fetchJson<RevenueResponse>(`${API_BASE}/api/revenue-market-cap?${params.toString()}`, "营收数据加载失败");
      return normalizePoints(data.revenueBars, years);
    },
  },
  {
    id: "netProfit",
    label: "归母净利润",
    unit: "亿元",
    description: "比较盈利规模与波动",
    enabled: true,
    load: async (stock, years) => {
      const params = new URLSearchParams({ stock, years });
      const data = await fetchJson<ProfitResponse>(`${API_BASE}/api/profit-market-cap?${params.toString()}`, "净利润数据加载失败");
      return normalizePoints(data.profitBars, years);
    },
  },
  {
    id: "operatingCashFlow",
    label: "经营活动现金流净额",
    unit: "亿元",
    description: "观察利润兑现成现金的能力",
    enabled: true,
    load: async (stock, years) => {
      const params = new URLSearchParams({ stock, years });
      const data = await fetchJson<CashFlowResponse>(`${API_BASE}/api/cash-flow-quality?${params.toString()}`, "现金流数据加载失败");
      return normalizePoints(data.operatingCashFlow, years);
    },
  },
  { id: "deductedNetProfit", label: "扣非归母净利润", unit: "亿元", description: "待接入利润表扣非口径", enabled: false, dataGap: "后端接口待接入" },
  { id: "grossMargin", label: "毛利率", unit: "%", description: "待接入利润率口径", enabled: false, dataGap: "后端接口待接入" },
  { id: "netMargin", label: "净利率", unit: "%", description: "待接入利润率口径", enabled: false, dataGap: "后端接口待接入" },
  { id: "roe", label: "ROE", unit: "%", description: "待接入加权 ROE 口径", enabled: false, dataGap: "后端接口待接入" },
  { id: "debtRatio", label: "资产负债率", unit: "%", description: "待接入资产负债表口径", enabled: false, dataGap: "后端接口待接入" },
  { id: "eps", label: "每股收益 EPS", unit: "元/股", description: "待接入基本 EPS 口径", enabled: false, dataGap: "后端接口待接入" },
];

function findCompany(input: string) {
  const keyword = input.trim().toLowerCase();
  if (!keyword) return null;
  return (
    COMPANIES.find((item) => item.code === keyword || item.name.toLowerCase() === keyword) ??
    COMPANIES.find((item) => item.code.includes(keyword) || item.name.toLowerCase().includes(keyword)) ?? {
      code: keyword,
      name: keyword,
    }
  );
}

function formatNumber(value?: number | null, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function indexedPoints(points: MetricPoint[]) {
  const base = points.find((item) => typeof item.value === "number" && item.value !== 0)?.value;
  if (!base) return points.map((item) => ({ ...item, value: null }));
  return points.map((item) => ({
    ...item,
    value: typeof item.value === "number" ? (item.value / base) * 100 : null,
  }));
}

export default function PerformanceCompareClient() {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [metricId, setMetricId] = useState<MetricId>("revenue");
  const [chartMode, setChartMode] = useState<ChartMode>("sameAxis");
  const [years, setYears] = useState<TimeRange>("10");
  const [input, setInput] = useState("");
  const [series, setSeries] = useState<CompanySeries[]>([]);
  const [error, setError] = useState("");

  const activeMetric = METRICS.find((item) => item.id === metricId) ?? METRICS[0];
  const suggestions = useMemo(() => {
    const keyword = input.trim().toLowerCase();
    if (!keyword) return COMPANIES.slice(0, 4);
    return COMPANIES.filter((item) => item.code.includes(keyword) || item.name.toLowerCase().includes(keyword)).slice(0, 6);
  }, [input]);

  async function loadCompany(company: Company, metric = activeMetric, range = years): Promise<CompanySeries> {
    if (!metric.load) {
      return { ...company, points: [], status: "error", error: "该指标暂未接入数据接口" };
    }
    try {
      const points = await metric.load(company.code, range);
      return { ...company, points, status: "loaded" };
    } catch (loadError) {
      return {
        ...company,
        points: [],
        status: "error",
        error: loadError instanceof Error ? loadError.message : "数据加载失败",
      };
    }
  }

  async function addCompany(company: Company) {
    setError("");
    if (series.some((item) => item.code === company.code)) {
      setError(`${company.name} 已经在图表里`);
      return;
    }
    if (series.length >= MAX_COMPANIES) {
      setError(`最多添加 ${MAX_COMPANIES} 家公司，先删掉一家公司再继续添加`);
      return;
    }
    setSeries((current) => [...current, { ...company, points: [], status: "loading" }]);
    const loaded = await loadCompany(company);
    setSeries((current) => current.map((item) => (item.code === company.code ? loaded : item)));
    setInput("");
  }

  async function reloadAll(nextMetric = activeMetric, nextYears = years) {
    setError("");
    setSeries((current) => current.map((item) => ({ ...item, status: "loading", error: undefined })));
    const loaded = await Promise.all(series.map((company) => loadCompany(company, nextMetric, nextYears)));
    setSeries(loaded);
  }

  useEffect(() => {
    if (!chartRef.current) return;
    chart.current = echarts.init(chartRef.current);
    const handleResize = () => chart.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chart.current) return;
    const loadedSeries = series.filter((item) => item.status === "loaded");
    const yearsOnAxis = Array.from(new Set(loadedSeries.flatMap((item) => item.points.map((point) => point.date)))).sort();
    const displayUnit = chartMode === "indexed" ? "指数" : activeMetric.unit;
    const toData = (item: CompanySeries) => {
      const points = chartMode === "indexed" ? indexedPoints(item.points) : item.points;
      return yearsOnAxis.map((year) => points.find((point) => point.date === year)?.value ?? null);
    };

    chart.current.setOption(
      {
        color: ["#007c89", "#b7791f", "#2264d1", "#087f5b", "#c0362c", "#7c3aed", "#0f766e", "#ea580c"],
        tooltip: {
          trigger: "axis",
          valueFormatter: (value: unknown) => `${formatNumber(typeof value === "number" ? value : null)} ${displayUnit}`,
        },
        legend: { top: 0, type: "scroll" },
        grid: { left: 58, right: chartMode === "dualAxis" ? 58 : 24, top: 52, bottom: 38 },
        xAxis: { type: "category", data: yearsOnAxis, boundaryGap: false },
        yAxis:
          chartMode === "dualAxis"
            ? [
                { type: "value", name: displayUnit, splitLine: { lineStyle: { color: "rgba(18,18,18,0.12)" } } },
                { type: "value", name: displayUnit, splitLine: { show: false } },
              ]
            : { type: "value", name: displayUnit, splitLine: { lineStyle: { color: "rgba(18,18,18,0.12)" } } },
        series: loadedSeries.map((item, index) => ({
          name: item.name,
          type: "line",
          smooth: true,
          showSymbol: true,
          symbolSize: 7,
          connectNulls: false,
          yAxisIndex: chartMode === "dualAxis" && index > 0 ? 1 : 0,
          data: toData(item),
        })),
      },
      { notMerge: true }
    );
    requestAnimationFrame(() => chart.current?.resize());
  }, [series, chartMode, activeMetric]);

  useEffect(() => {
    if (!series.length) return;
    void reloadAll(activeMetric, years);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metricId, years]);

  const latestRows = series.map((item) => {
    const latest = item.points.at(-1);
    const first = item.points.find((point) => typeof point.value === "number");
    const change =
      first?.value && latest?.value !== null && latest?.value !== undefined ? ((latest.value - first.value) / Math.abs(first.value)) * 100 : null;
    return { ...item, latest, change };
  });

  return (
    <AppShell active="performanceCompare">
      <section className="compare-hero" aria-label="业绩对比">
        <div>
          <div className="summary-kicker">Performance Compare</div>
          <h1>A股公司业绩对比</h1>
          <p>选择一个财务指标，把多家公司逐个添加到同一张图里，快速比较历史表现、规模差异和增长速度。</p>
        </div>
        <div className="compare-add-panel">
          <label>
            股票代码或公司名称
            <div className="compare-search-row">
              <input
                value={input}
                placeholder="例如 600519 或 贵州茅台"
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    const company = findCompany(input);
                    if (company) void addCompany(company);
                  }
                }}
              />
              <button
                type="button"
                onClick={() => {
                  const company = findCompany(input);
                  if (company) void addCompany(company);
                }}
              >
                添加
              </button>
            </div>
          </label>
          <div className="compare-suggestion-row">
            {suggestions.map((item) => (
              <button key={item.code} type="button" onClick={() => void addCompany(item)}>
                {item.name}
                <span>{item.code}</span>
              </button>
            ))}
          </div>
          {error ? <div className="compare-error">{error}</div> : null}
        </div>
      </section>

      <section className="compare-workbench">
        <div className="compare-control-strip">
          <div className="compare-control-group metric-grid" aria-label="指标选择">
            {METRICS.map((metric) => (
              <button
                key={metric.id}
                type="button"
                className={metric.id === metricId ? "active" : ""}
                disabled={!metric.enabled}
                title={metric.dataGap || metric.description}
                onClick={() => setMetricId(metric.id)}
              >
                <strong>{metric.label}</strong>
                <span>{metric.enabled ? metric.description : metric.dataGap}</span>
              </button>
            ))}
          </div>

          <div className="compare-segment-row">
            <div className="compare-control-group compact">
              {[
                { value: "5", label: "最近 5 年" },
                { value: "10", label: "最近 10 年" },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={years === item.value ? "active" : ""}
                  onClick={() => setYears(item.value as TimeRange)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="compare-control-group compact">
              {[
                { value: "sameAxis", label: "同一坐标轴" },
                { value: "dualAxis", label: "双坐标轴" },
                { value: "indexed", label: "指数化对比" },
              ].map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={chartMode === item.value ? "active" : ""}
                  onClick={() => setChartMode(item.value as ChartMode)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="compare-chart-card">
          <div className="compare-chart-head">
            <div>
              <h2>{activeMetric.label}</h2>
              <p>
                {chartMode === "indexed"
                  ? "每家公司首个有效年份设为 100，用来比较增长速度。"
                  : `单位：${activeMetric.unit}。缺失年份不会补 0，会在图表上保留断点。`}
              </p>
            </div>
            <button type="button" onClick={() => void reloadAll()}>
              刷新数据
            </button>
          </div>
          <div ref={chartRef} className="compare-chart-box" />
          {!series.length ? <div className="compare-empty">先从右上方或快捷公司里添加一家公司。</div> : null}
        </div>

        <div className="compare-company-grid">
          {latestRows.map((item) => (
            <article key={item.code} className={`compare-company-card ${item.status}`}>
              <div>
                <strong>{item.name}</strong>
                <span>{item.code}</span>
              </div>
              <div>
                <b>
                  {item.status === "loading"
                    ? "加载中"
                    : item.status === "error"
                      ? "失败"
                      : `${formatNumber(item.latest?.value)} ${activeMetric.unit}`}
                </b>
                <em>
                  {item.status === "error"
                    ? item.error
                    : item.latest
                      ? `${item.latest.date} | 区间变化 ${item.change === null ? "-" : `${formatNumber(item.change)}%`}`
                      : "暂无有效数据"}
                </em>
              </div>
              <button type="button" aria-label={`删除 ${item.name}`} onClick={() => setSeries((current) => current.filter((row) => row.code !== item.code))}>
                删除
              </button>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
