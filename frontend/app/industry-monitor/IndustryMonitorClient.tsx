"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell, SectionShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

type IndustryCell = string | number | boolean | null;

type IndustryTablePreview = {
  status: "ok" | "empty" | "error" | string;
  columns: string[];
  rows: Array<Record<string, IndustryCell>>;
  rowCount?: number;
  error?: string;
};

type IndustryIndicatorGroup = {
  status: string;
  source: string;
  tables: Record<string, IndustryTablePreview>;
  dataGaps?: string[];
};

type IndustryModulePayload = {
  tool: string;
  status: string;
  stock: string;
  metrics?: Record<string, unknown>;
  source?: string[];
  dataGaps?: string[];
};

type IndustryDataResponse = {
  tool: string;
  status: "ok" | "partial" | string;
  industries: string[];
  industryInference?: {
    mode?: string;
    modules?: string[];
    input?: string | null;
    evidence?: string[];
  };
  data: Record<string, IndustryModulePayload>;
  errors: Record<string, string>;
  source: string[];
  fetchedAt?: string;
};

type QueryState = {
  years: string;
  industries: string;
};

type IndustryChoice = QueryState & {
  label: string;
  focus: string;
};

type MetricPoint = {
  label: string;
  value: number;
};

type MonitorMetric = {
  id: string;
  moduleKey: string;
  moduleLabel: string;
  groupTitle?: string;
  title: string;
  status: string;
  source?: string;
  valueLabel: string;
  value: number | null;
  previousValue: number | null;
  delta: number | null;
  deltaPct: number | null;
  dateLabel: string;
  unit: string;
  points: MetricPoint[];
  rows: IndustryTablePreview["rows"];
  columns: string[];
  error?: string;
};

type CommodityQuote = {
  symbol: string;
  name: string;
  price: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  lastSettlePrice: number | null;
  volume: number | null;
  unit: string;
};

type CommoditySeries = {
  symbol: string;
  name: string;
  unit: string;
  points: MetricPoint[];
};

const INDUSTRY_CHOICES: IndustryChoice[] = [
  { industries: "baijiu", years: "8", label: "白酒", focus: "批价、渠道、产销、库存" },
  { industries: "nonferrous_chemical", years: "8", label: "有色/化工", focus: "商品价格、能源成本、产销披露" },
  { industries: "shipping", years: "8", label: "航运", focus: "运价指数、燃油、吞吐量" },
  { industries: "financial", years: "8", label: "金融", focus: "利率、社融、公司金融指标" },
  { industries: "game_internet", years: "8", label: "游戏/互联网", focus: "用户、流水、版号、票房代理" },
  { industries: "auto_new_energy", years: "8", label: "汽车新能源", focus: "销量、出口、电池材料" },
];

const MODULE_LABELS: Record<string, string> = {
  baijiu: "白酒",
  nonferrous_chemical: "有色/化工",
  shipping: "航运",
  financial: "金融",
  game_internet: "游戏/互联网",
  auto_new_energy: "汽车新能源",
};

const GROUP_LABELS: Record<string, string> = {
  macroOperatingIndicators: "需求景气",
  customsTradeIndicators: "进出口",
  energyCostIndicators: "能源成本",
};

const TABLE_LABELS: Record<string, string> = {
  industrialProductionYoy: "工业增加值同比",
  industrialValueAdded: "工业增加值",
  manufacturingPmi: "制造业 PMI",
  ppi: "PPI",
  electricityConsumption: "全社会用电量",
  enterpriseBoomIndex: "企业景气指数",
  customsImportExportOverview: "进出口总览",
  exportsYoyUsd: "出口同比",
  importsYoyUsd: "进口同比",
  tradeBalanceUsd: "贸易差额",
  oilPriceAdjustments: "油价调整",
  dailyEnergyInventory: "能源库存",
  energyIndex: "能源指数",
  domesticCarbonMarket: "碳市场",
  commodityPrices: "商品价格",
  freightIndices: "航运指数",
  fuelPrices: "燃油价格",
  bdi: "BDI",
  bci: "BCI",
  bpi: "BPI",
  bcti: "BCTI",
  bdti: "BDTI",
  chinaFreightIndex: "中国运价指数",
  cpcaTotalRetail: "乘用车零售",
  cpcaTotalWholesale: "乘用车批发",
  cpcaTotalExport: "乘用车出口",
  cpcaNewEnergy: "新能源渗透",
  batteryMaterials: "电池材料",
  lpr: "LPR",
  moneySupply: "货币供应",
  newCredit: "新增信贷",
  insuranceIncome: "保险收入",
  movieBoxOfficeProxy: "票房代理",
};

const DATE_KEYWORDS = ["日期", "月份", "时间", "报告期", "period", "date", "month", "time"];
const VALUE_PRIORITY = [
  "今值",
  "最新价",
  "现价",
  "收盘价",
  "价格",
  "close",
  "value",
  "指数",
  "当月出口额-同比增长",
  "当月进口额-同比增长",
  "贸易差额",
  "成交均价",
  "成交价",
  "收盘",
  "累计",
  "同比",
  "环比",
  "金额",
];

function readQueryState(): QueryState {
  if (typeof window === "undefined") return { years: "8", industries: "baijiu" };
  const params = new URLSearchParams(window.location.search);
  const industries = params.get("industries")?.trim() || "baijiu";
  const matchedChoice = INDUSTRY_CHOICES.find((item) => item.industries === industries);
  return {
    years: params.get("years")?.trim() || matchedChoice?.years || "8",
    industries: matchedChoice?.industries || "baijiu",
  };
}

function formatNumber(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

function valueDigits(value?: number | null) {
  return Math.abs(value ?? 0) >= 100 ? 0 : 2;
}

function formatValueWithUnit(value?: number | null, unit = "") {
  const formatted = formatNumber(value, valueDigits(value));
  return unit ? `${formatted}${unit}` : formatted;
}

function summarizePoints(points: MetricPoint[]) {
  const valid = points.filter((point) => Number.isFinite(point.value));
  if (!valid.length) return null;
  const first = valid[0];
  const latest = valid[valid.length - 1];
  const min = valid.reduce((best, point) => (point.value < best.value ? point : best), valid[0]);
  const max = valid.reduce((best, point) => (point.value > best.value ? point : best), valid[0]);
  const delta = latest.value - first.value;
  const deltaPct = first.value === 0 ? null : (delta / Math.abs(first.value)) * 100;
  return { first, latest, min, max, delta, deltaPct, count: valid.length };
}

function formatAxisValue(value: number) {
  return formatNumber(value, Math.abs(value) >= 100 ? 0 : 2);
}

function formatCell(value: IndustryCell | undefined) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isFinite(value) ? formatNumber(value, Math.abs(value) >= 100 ? 0 : 2) : "-";
  return String(value);
}

function toNumber(value: IndustryCell | undefined): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const cleaned = value.replace(/,/g, "").replace(/%/g, "").trim();
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function recordNumber(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") return toNumber(value);
  return null;
}

function recordString(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function isTablePreview(value: unknown): value is IndustryTablePreview {
  return Boolean(value && typeof value === "object" && "rows" in value && "columns" in value && "status" in value);
}

function isIndicatorGroup(value: unknown): value is IndustryIndicatorGroup {
  return Boolean(value && typeof value === "object" && "tables" in value && "source" in value);
}

function isTableCollection(value: unknown): value is Record<string, IndustryTablePreview> {
  return Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.values(value).some((item) => isTablePreview(item)),
  );
}

function findDateColumn(columns: string[]) {
  return columns.find((column) => DATE_KEYWORDS.some((keyword) => column.toLowerCase().includes(keyword.toLowerCase())));
}

function numericColumns(table: IndustryTablePreview) {
  return table.columns.filter((column) => table.rows.some((row) => toNumber(row[column]) !== null));
}

function scoreValueColumn(column: string) {
  const normalized = column.toLowerCase();
  const index = VALUE_PRIORITY.findIndex((keyword) => normalized.includes(keyword.toLowerCase()));
  return index === -1 ? VALUE_PRIORITY.length + normalized.length / 100 : index;
}

function findValueColumn(table: IndustryTablePreview) {
  const dateColumn = findDateColumn(table.columns);
  const candidates = numericColumns(table).filter((column) => column !== dateColumn);
  return candidates.sort((left, right) => scoreValueColumn(left) - scoreValueColumn(right))[0] || candidates[0] || "";
}

function inferUnit(column: string, value: number | null) {
  if (column.includes("%") || column.includes("同比") || column.includes("环比") || column.toLowerCase().includes("rate")) return "%";
  if (column.includes("价格") || column.includes("价") || column.includes("金额") || column.includes("收入")) return "";
  if (column.toLowerCase().includes("pmi")) return "";
  if (value !== null && Math.abs(value) <= 100 && (column.includes("今值") || column.includes("前值"))) return "%";
  return "";
}

function buildPoints(table: IndustryTablePreview, valueColumn: string, dateColumn?: string): MetricPoint[] {
  if (!valueColumn) return [];
  return table.rows
    .map((row, index) => ({
      label: dateColumn ? formatCell(row[dateColumn]) : String(index + 1),
      value: toNumber(row[valueColumn]),
    }))
    .filter((point): point is MetricPoint => point.value !== null);
}

function buildMetricFromTable(
  moduleKey: string,
  groupKey: string | null,
  tableKey: string,
  table: IndustryTablePreview,
  source?: string,
): MonitorMetric {
  const valueColumn = findValueColumn(table);
  const dateColumn = findDateColumn(table.columns);
  const points = buildPoints(table, valueColumn, dateColumn);
  const latestPoint = points[points.length - 1];
  const previousPoint = points[points.length - 2];
  const delta = latestPoint && previousPoint ? latestPoint.value - previousPoint.value : null;
  const deltaPct = latestPoint && previousPoint && previousPoint.value !== 0 ? (delta! / Math.abs(previousPoint.value)) * 100 : null;
  const moduleLabel = MODULE_LABELS[moduleKey] || moduleKey;
  return {
    id: `${moduleKey}-${groupKey || "special"}-${tableKey}`,
    moduleKey,
    moduleLabel,
    groupTitle: groupKey ? GROUP_LABELS[groupKey] || groupKey : undefined,
    title: TABLE_LABELS[tableKey] || tableKey,
    status: table.status,
    source,
    valueLabel: valueColumn || "数值",
    value: latestPoint?.value ?? null,
    previousValue: previousPoint?.value ?? null,
    delta,
    deltaPct,
    dateLabel: latestPoint?.label || "-",
    unit: inferUnit(valueColumn, latestPoint?.value ?? null),
    points,
    rows: table.rows,
    columns: table.columns,
    error: table.error,
  };
}

function collectMonitorMetrics(industryData?: IndustryDataResponse | null) {
  const metrics: MonitorMetric[] = [];
  Object.entries(industryData?.data ?? {}).forEach(([moduleKey, modulePayload]) => {
    Object.entries(modulePayload.metrics ?? {}).forEach(([metricKey, metricValue]) => {
      if (isIndicatorGroup(metricValue)) {
        Object.entries(metricValue.tables ?? {}).forEach(([tableKey, table]) => {
          metrics.push(buildMetricFromTable(moduleKey, metricKey, tableKey, table, metricValue.source));
        });
        return;
      }
      if (isTablePreview(metricValue)) {
        metrics.push(buildMetricFromTable(moduleKey, null, metricKey, metricValue, modulePayload.source?.join("、")));
        return;
      }
      if (isTableCollection(metricValue)) {
        Object.entries(metricValue).forEach(([tableKey, table]) => {
          if (isTablePreview(table)) {
            metrics.push(buildMetricFromTable(moduleKey, metricKey, tableKey, table, modulePayload.source?.join("、")));
          }
        });
      }
    });
  });
  return metrics;
}

function getNonferrousModule(industryData?: IndustryDataResponse | null) {
  return industryData?.data?.nonferrous_chemical ?? null;
}

function getCommodityMetrics(modulePayload?: IndustryModulePayload | null, metricKey = "commodityPrices") {
  const commodityPrices = modulePayload?.metrics?.[metricKey];
  if (!isRecord(commodityPrices)) return null;
  const metrics = commodityPrices.metrics;
  return isRecord(metrics) ? metrics : null;
}

function collectCommodityQuotes(modulePayload?: IndustryModulePayload | null, metricKey = "commodityPrices"): CommodityQuote[] {
  const metrics = getCommodityMetrics(modulePayload, metricKey);
  const rows = metrics?.realtimeFutures;
  if (!Array.isArray(rows)) return [];
  return rows.filter(isRecord).map((row) => ({
    symbol: recordString(row, "symbol"),
    name: recordString(row, "name") || recordString(row, "contract"),
    price: recordNumber(row, "price"),
    open: recordNumber(row, "open"),
    high: recordNumber(row, "high"),
    low: recordNumber(row, "low"),
    lastSettlePrice: recordNumber(row, "lastSettlePrice"),
    volume: recordNumber(row, "volume"),
    unit: recordString(row, "unit"),
  }));
}

function collectCommoditySeries(modulePayload?: IndustryModulePayload | null, metricKey = "commodityPrices"): CommoditySeries[] {
  const metrics = getCommodityMetrics(modulePayload, metricKey);
  const rows = metrics?.spotBasisSeries;
  if (!Array.isArray(rows)) return [];
  const grouped = new Map<string, { name: string; unit: string; points: MetricPoint[] }>();
  rows.filter(isRecord).forEach((row) => {
    const symbol = recordString(row, "symbol");
    const value = recordNumber(row, "spotPrice");
    if (!symbol || value === null) return;
    const current = grouped.get(symbol) ?? {
      name: recordString(row, "name") || symbol,
      unit: recordString(row, "unit"),
      points: [],
    };
    current.points.push({ label: recordString(row, "date"), value });
    grouped.set(symbol, current);
  });
  return Array.from(grouped.entries()).map(([symbol, item]) => ({
    symbol,
    name: item.name,
    unit: item.unit,
    points: item.points,
  }));
}

function isFreightMetric(metric: MonitorMetric) {
  return metric.groupTitle === GROUP_LABELS.freightIndices || metric.groupTitle === "freightIndices";
}

function isCommonOperatingMetric(metric: MonitorMetric) {
  return (
    metric.groupTitle === GROUP_LABELS.macroOperatingIndicators ||
    metric.groupTitle === "macroOperatingIndicators" ||
    metric.groupTitle === GROUP_LABELS.customsTradeIndicators ||
    metric.groupTitle === "customsTradeIndicators" ||
    metric.groupTitle === GROUP_LABELS.energyCostIndicators ||
    metric.groupTitle === "energyCostIndicators"
  );
}

function isSpecialMetric(moduleKey: string, metric: MonitorMetric) {
  if (moduleKey === "nonferrous_chemical") return metric.groupTitle === GROUP_LABELS.energyCostIndicators;
  if (moduleKey === "shipping") return isFreightMetric(metric);
  return !isCommonOperatingMetric(metric);
}

function isIndustryOverviewMetric(moduleKey: string, metric: MonitorMetric) {
  if (moduleKey === "nonferrous_chemical") {
    return metric.groupTitle === GROUP_LABELS.energyCostIndicators || !metric.groupTitle;
  }
  if (moduleKey === "shipping") {
    return isFreightMetric(metric) || !metric.groupTitle;
  }
  return !metric.groupTitle;
}

function Sparkline({ points }: { points: MetricPoint[] }) {
  const validPoints = points.filter((point) => Number.isFinite(point.value));
  const values = validPoints.map((point) => point.value);
  if (values.length < 2) return <div className="industry-sparkline-empty">趋势不足</div>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const left = 22;
  const right = 98;
  const top = 6;
  const bottom = 30;
  const width = right - left;
  const height = bottom - top;
  const polyline = values
    .map((value, index) => {
      const x = values.length === 1 ? left : left + (index / (values.length - 1)) * width;
      const y = bottom - ((value - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg className="industry-sparkline" viewBox="0 0 100 40" role="img" aria-label="趋势图">
      <line className="industry-chart-grid" x1={left} y1={top} x2={right} y2={top} />
      <line className="industry-chart-grid" x1={left} y1={bottom} x2={right} y2={bottom} />
      <line className="industry-chart-axis" x1={left} y1={top} x2={left} y2={bottom} />
      <line className="industry-chart-axis" x1={left} y1={bottom} x2={right} y2={bottom} />
      <text className="industry-chart-label" x="2" y={top + 3}>{formatAxisValue(max)}</text>
      <text className="industry-chart-label" x="2" y={bottom + 3}>{formatAxisValue(min)}</text>
      <text className="industry-chart-label industry-chart-x-label" x={left} y="38">{validPoints[0]?.label || ""}</text>
      <text className="industry-chart-label industry-chart-x-label" x={right} y="38" textAnchor="end">{validPoints[validPoints.length - 1]?.label || ""}</text>
      <polyline points={polyline} fill="none" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      {values.map((value, index) => {
        const x = values.length === 1 ? left : left + (index / (values.length - 1)) * width;
        const y = bottom - ((value - min) / range) * height;
        return <circle key={`${value}-${index}`} cx={x} cy={y} r={index === values.length - 1 ? 3 : 1.8} />;
      })}
    </svg>
  );
}

function LineChart({ points }: { points: MetricPoint[] }) {
  const validPoints = points.filter((point) => Number.isFinite(point.value));
  const values = validPoints.map((point) => point.value);
  if (values.length < 2) return <div className="industry-sparkline-empty">趋势不足</div>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const mid = min + range / 2;
  const left = 18;
  const right = 98;
  const top = 12;
  const midY = 48;
  const bottom = 78;
  const width = right - left;
  const height = bottom - top;
  const polyline = values
    .map((value, index) => {
      const x = values.length === 1 ? left : left + (index / (values.length - 1)) * width;
      const y = bottom - ((value - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg className="industry-line-chart" viewBox="0 0 100 96" role="img" aria-label="价格趋势图">
      <line className="industry-chart-grid" x1={left} y1={top} x2={right} y2={top} />
      <line className="industry-chart-grid" x1={left} y1={midY} x2={right} y2={midY} />
      <line className="industry-chart-grid" x1={left} y1={bottom} x2={right} y2={bottom} />
      <line className="industry-chart-axis" x1={left} y1={top} x2={left} y2={bottom} />
      <line className="industry-chart-axis" x1={left} y1={bottom} x2={right} y2={bottom} />
      <text className="industry-chart-label" x="2" y={top + 3}>{formatAxisValue(max)}</text>
      <text className="industry-chart-label" x="2" y={midY + 3}>{formatAxisValue(mid)}</text>
      <text className="industry-chart-label" x="2" y={bottom + 3}>{formatAxisValue(min)}</text>
      <text className="industry-chart-label industry-chart-x-label" x={left} y="92">{validPoints[0]?.label || ""}</text>
      <text className="industry-chart-label industry-chart-x-label" x={right} y="92" textAnchor="end">{validPoints[validPoints.length - 1]?.label || ""}</text>
      <polyline points={polyline} fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function TrendRangeSummary({ points, unit = "" }: { points: MetricPoint[]; unit?: string }) {
  const summary = summarizePoints(points);
  if (!summary) return null;
  return (
    <div className="trend-range-summary">
      <div>
        <span>区间变化</span>
        <strong>
          {formatValueWithUnit(summary.first.value, unit)}
          <i>→</i>
          {formatValueWithUnit(summary.latest.value, unit)}
        </strong>
        <small>
          {summary.first.label || "起点"} 至 {summary.latest.label || "最新"}
        </small>
      </div>
      <div>
        <span>最低 / 最高</span>
        <strong>
          {formatValueWithUnit(summary.min.value, unit)}
          <i>/</i>
          {formatValueWithUnit(summary.max.value, unit)}
        </strong>
        <small>
          {summary.min.label || "-"} / {summary.max.label || "-"}
        </small>
      </div>
      <div>
        <span>累计涨跌</span>
        <strong>{`${summary.delta > 0 ? "+" : ""}${formatValueWithUnit(summary.delta, unit)}`}</strong>
        <small>{summary.deltaPct === null ? `${summary.count} 个观测点` : `${summary.deltaPct > 0 ? "+" : ""}${formatNumber(summary.deltaPct, 2)}%`}</small>
      </div>
    </div>
  );
}

function CommodityQuoteCard({ quote }: { quote: CommodityQuote }) {
  const range = quote.high !== null && quote.low !== null ? Math.max(quote.high - quote.low, 1) : 1;
  const openPosition = quote.open !== null && quote.low !== null ? ((quote.open - quote.low) / range) * 100 : 50;
  const pricePosition = quote.price !== null && quote.low !== null ? ((quote.price - quote.low) / range) * 100 : 50;
  const delta = quote.price !== null && quote.lastSettlePrice !== null ? quote.price - quote.lastSettlePrice : null;
  const deltaPct = delta !== null && quote.lastSettlePrice ? (delta / Math.abs(quote.lastSettlePrice)) * 100 : null;
  return (
    <article className="commodity-quote-card">
      <div className="industry-detail-title">
        <span>{quote.name || quote.symbol}</span>
        <em>{quote.symbol}</em>
      </div>
      <div className="industry-monitor-value">
        {formatNumber(quote.price, Math.abs(quote.price ?? 0) >= 100 ? 0 : 2)}
        {quote.unit ? <small>{quote.unit}</small> : null}
      </div>
      <div className="commodity-range">
        <i style={{ left: `${Math.max(0, Math.min(openPosition, 100))}%` }} />
        <b style={{ left: `${Math.max(0, Math.min(pricePosition, 100))}%` }} />
      </div>
      <div className="commodity-range-summary">
        <span>日内区间</span>
        <strong>
          {formatValueWithUnit(quote.low, quote.unit)}
          <i>→</i>
          {formatValueWithUnit(quote.high, quote.unit)}
        </strong>
      </div>
      <div className="commodity-quote-meta">
        <span>开盘 {formatValueWithUnit(quote.open, quote.unit)}</span>
        <span>最新 {formatValueWithUnit(quote.price, quote.unit)}</span>
      </div>
      <div className="commodity-quote-meta">
        <span>较结算 {delta === null ? "-" : `${delta > 0 ? "+" : ""}${formatValueWithUnit(delta, quote.unit)}`}</span>
        <span>{deltaPct === null ? `量 ${formatNumber(quote.volume, 0)}` : `${deltaPct > 0 ? "+" : ""}${formatNumber(deltaPct, 2)}%`}</span>
      </div>
    </article>
  );
}

function CommoditySeriesCard({ series }: { series: CommoditySeries }) {
  const latest = series.points[series.points.length - 1];
  const previous = series.points[series.points.length - 2];
  const delta = latest && previous ? latest.value - previous.value : null;
  return (
    <article className="commodity-series-card">
      <div className="industry-detail-title">
        <span>{series.name}现货价</span>
        <em>{series.symbol}</em>
      </div>
      <div className="industry-monitor-value-row">
        <div>
          <div className="industry-monitor-value">
            {formatNumber(latest?.value, Math.abs(latest?.value ?? 0) >= 100 ? 0 : 2)}
            {series.unit ? <small>{series.unit}</small> : null}
          </div>
          <div className="industry-monitor-date">{latest?.label || "-"}</div>
        </div>
        <div className="industry-monitor-delta">
          <span>{delta === null ? "-" : `${delta > 0 ? "+" : ""}${formatNumber(delta, 2)}`}</span>
          <small>{series.points.length} 个交易日</small>
        </div>
      </div>
      <LineChart points={series.points} />
      <TrendRangeSummary points={series.points} unit={series.unit} />
    </article>
  );
}

function MetricCard({ metric }: { metric: MonitorMetric }) {
  const trendClass = metric.delta === null ? "flat" : metric.delta > 0 ? "up" : metric.delta < 0 ? "down" : "flat";
  return (
    <article className={`industry-monitor-card trend-${trendClass}`}>
      <div className="industry-monitor-card-top">
        <div>
          <div className="industry-monitor-eyebrow">
            {metric.moduleLabel}
            {metric.groupTitle ? ` / ${metric.groupTitle}` : ""}
          </div>
          <h3>{metric.title}</h3>
        </div>
        <span className="industry-status-chip">{metric.status}</span>
      </div>
      <div className="industry-monitor-value-row">
        <div>
          <div className="industry-monitor-value">
            {formatNumber(metric.value, Math.abs(metric.value ?? 0) >= 100 ? 0 : 2)}
            {metric.unit ? <small>{metric.unit}</small> : null}
          </div>
          <div className="industry-monitor-date">{metric.dateLabel}</div>
        </div>
        <div className="industry-monitor-delta">
          <span>{metric.delta === null ? "持平/缺少上期" : `${metric.delta > 0 ? "+" : ""}${formatNumber(metric.delta, 2)}`}</span>
          <small>{metric.deltaPct === null ? metric.valueLabel : `${metric.deltaPct > 0 ? "+" : ""}${formatNumber(metric.deltaPct, 2)}%`}</small>
        </div>
      </div>
      <Sparkline points={metric.points} />
      <TrendRangeSummary points={metric.points} unit={metric.unit} />
      <div className="industry-monitor-foot">
        <span>{metric.valueLabel}</span>
        <span>{metric.points.length} 个观测点</span>
      </div>
      {metric.error ? <div className="industry-error-text">{metric.error}</div> : null}
    </article>
  );
}

function DetailTable({ metric }: { metric: MonitorMetric }) {
  const visibleColumns = metric.columns.slice(0, 5);
  return (
    <div className="industry-detail-table">
      <div className="industry-detail-title">
        <span>{metric.title}</span>
        <em>{metric.moduleLabel}</em>
      </div>
      <div className="industry-detail-grid" style={{ gridTemplateColumns: `repeat(${Math.max(visibleColumns.length, 1)}, minmax(0, 1fr))` }}>
        {visibleColumns.map((column) => (
          <b key={`${metric.id}-${column}`}>{column}</b>
        ))}
        {metric.rows.slice(-4).map((row, rowIndex) =>
          visibleColumns.map((column) => (
            <span key={`${metric.id}-${rowIndex}-${column}`}>{formatCell(row[column])}</span>
          )),
        )}
      </div>
    </div>
  );
}

function IndustrySpecificPanel({
  query,
  modulePayload,
  metrics,
}: {
  query: QueryState;
  modulePayload: IndustryModulePayload | null;
  metrics: MonitorMetric[];
}) {
  const title = MODULE_LABELS[query.industries] || "行业专项";
  const specialMetrics = metrics.filter((metric) => isSpecialMetric(query.industries, metric));
  const commodityQuotes = collectCommodityQuotes(modulePayload);
  const commoditySeries = collectCommoditySeries(modulePayload);
  const fuelQuotes = collectCommodityQuotes(modulePayload, "fuelPrices");
  const fuelSeries = collectCommoditySeries(modulePayload, "fuelPrices");
  const batteryQuotes = collectCommodityQuotes(modulePayload, "batteryMaterials");
  const batterySeries = collectCommoditySeries(modulePayload, "batteryMaterials");

  if (query.industries === "nonferrous_chemical") {
    const energyMetrics = metrics.filter((metric) => metric.groupTitle === GROUP_LABELS.energyCostIndicators);
    return (
      <SectionShell
        title="有色/化工专项监控"
        description="把商品期货、现货基差、能源成本和产销披露放到同一屏，直接看价格和经营变量。"
        meta={`${commodityQuotes.length} 个商品报价 / ${commoditySeries.length} 条现货序列`}
      >
        <div className="industry-subsection-title">
          <h3>商品期货报价</h3>
          <span>价格、开盘、高低区间、较结算变化</span>
        </div>
        <div className="commodity-quote-grid">
          {commodityQuotes.slice(0, 12).map((quote) => (
            <CommodityQuoteCard key={quote.symbol} quote={quote} />
          ))}
          {!commodityQuotes.length ? <div className="subtle">暂无商品期货报价。</div> : null}
        </div>

        <div className="industry-subsection-title">
          <h3>现货价格趋势</h3>
          <span>来自现货/基差序列，展示最近交易日走势</span>
        </div>
        <div className="commodity-series-grid">
          {commoditySeries.slice(0, 6).map((series) => (
            <CommoditySeriesCard key={series.symbol} series={series} />
          ))}
          {!commoditySeries.length ? <div className="subtle">暂无现货价格序列。</div> : null}
        </div>

        <div className="industry-subsection-title">
          <h3>能源成本走势</h3>
          <span>油价、能源库存、能源指数、碳市场等成本变量</span>
        </div>
        <div className="industry-monitor-grid">
          {energyMetrics.slice(0, 6).map((metric) => (
            <MetricCard key={metric.id} metric={metric} />
          ))}
          {!energyMetrics.length ? <div className="subtle">暂无能源成本图表。</div> : null}
        </div>
      </SectionShell>
    );
  }

  if (query.industries === "shipping") {
    const freightMetrics = metrics.filter(isFreightMetric);
    return (
      <SectionShell title="航运专项监控" description="直接展示运价指数和燃油价格。" meta={`${freightMetrics.length} 个运价指标`}>
        <div className="industry-subsection-title">
          <h3>运价指数</h3>
          <span>BDI、BCI、BPI、油轮指数和中国运价指数</span>
        </div>
        <div className="industry-monitor-grid">
          {freightMetrics.slice(0, 9).map((metric) => (
            <MetricCard key={metric.id} metric={metric} />
          ))}
          {!freightMetrics.length ? <div className="subtle">暂无运价指数。</div> : null}
        </div>

        <div className="industry-subsection-title">
          <h3>燃油价格</h3>
          <span>原油、燃油、低硫燃油等成本变量</span>
        </div>
        <div className="commodity-quote-grid">
          {fuelQuotes.slice(0, 6).map((quote) => (
            <CommodityQuoteCard key={quote.symbol} quote={quote} />
          ))}
          {!fuelQuotes.length ? <div className="subtle">暂无燃油报价。</div> : null}
        </div>
        <div className="commodity-series-grid">
          {fuelSeries.slice(0, 3).map((series) => (
            <CommoditySeriesCard key={series.symbol} series={series} />
          ))}
        </div>
      </SectionShell>
    );
  }

  if (query.industries === "financial") {
    return (
      <SectionShell
        title="金融专项监控"
        description="直接展示 LPR、货币供应、社融信贷和保险收入。"
        meta={`${specialMetrics.length} 个金融指标`}
      >
        <div className="industry-monitor-grid">
          {specialMetrics.slice(0, 9).map((metric) => (
            <MetricCard key={metric.id} metric={metric} />
          ))}
        </div>
        {!specialMetrics.length ? <div className="subtle">暂无金融专项指标。</div> : null}
      </SectionShell>
    );
  }

  if (query.industries === "auto_new_energy") {
    const autoMetrics = specialMetrics.filter((metric) => !metric.id.includes("batteryMaterials"));
    return (
      <SectionShell title="汽车新能源专项监控" description="直接展示乘联会销量、批发、出口、新能源渗透和电池材料价格。" meta={`${autoMetrics.length} 个汽车指标`}>
        <div className="industry-subsection-title">
          <h3>销量/批发/出口</h3>
          <span>乘联会整体市场指标</span>
        </div>
        <div className="industry-monitor-grid">
          {autoMetrics.slice(0, 9).map((metric) => (
            <MetricCard key={metric.id} metric={metric} />
          ))}
          {!autoMetrics.length ? <div className="subtle">暂无汽车销量指标。</div> : null}
        </div>

        <div className="industry-subsection-title">
          <h3>电池材料价格</h3>
          <span>锂、镍、铜、铝、工业硅等材料报价和趋势</span>
        </div>
        <div className="commodity-quote-grid">
          {batteryQuotes.slice(0, 8).map((quote) => (
            <CommodityQuoteCard key={quote.symbol} quote={quote} />
          ))}
          {!batteryQuotes.length ? <div className="subtle">暂无电池材料报价。</div> : null}
        </div>
        <div className="commodity-series-grid">
          {batterySeries.slice(0, 4).map((series) => (
            <CommoditySeriesCard key={series.symbol} series={series} />
          ))}
        </div>

      </SectionShell>
    );
  }

  return (
    <SectionShell title={`${title}专项监控`} description="展示当前行业模块自己的固定专项指标，避免只看通用宏观数据。" meta={`${specialMetrics.length} 个专项项`}>
      <div className="industry-monitor-grid">
        {specialMetrics.slice(0, 9).map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </div>
      {!specialMetrics.length ? <div className="subtle">暂无专项数据。</div> : null}
    </SectionShell>
  );
}

export default function IndustryMonitorClient() {
  const initialQuery = useRef(readQueryState());
  const [query, setQuery] = useState<QueryState>(initialQuery.current);
  const [industryData, setIndustryData] = useState<IndustryDataResponse | null>(null);
  const [status, setStatus] = useState("正在加载行业数据");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  const monitorMetrics = useMemo(() => collectMonitorMetrics(industryData), [industryData]);
  const activeModules = industryData?.industries ?? [];
  const selectedModuleKey = query.industries;
  const selectedMonitorMetrics = monitorMetrics.filter((metric) => metric.moduleKey === selectedModuleKey);
  const headlineMetrics = selectedMonitorMetrics
    .filter((metric) => metric.value !== null && isIndustryOverviewMetric(selectedModuleKey, metric))
    .slice(0, 9);
  const detailMetrics = selectedMonitorMetrics.filter((metric) => isIndustryOverviewMetric(selectedModuleKey, metric)).slice(0, 8);
  const moduleText = MODULE_LABELS[selectedModuleKey] || activeModules.map((item) => MODULE_LABELS[item] || item).join("、") || "白酒";

  function syncUrl(nextQuery: QueryState) {
    const params = new URLSearchParams(nextQuery);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }

  async function loadIndustryData(nextQuery = query, refresh = false) {
    abortRef.current?.abort();
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    setIsLoading(true);
    setStatus(refresh ? "正在刷新行业数据" : "正在加载行业数据");
    setError(null);
    setQuery(nextQuery);
    syncUrl(nextQuery);

    try {
      const params = new URLSearchParams({
        years: nextQuery.years,
        industries: nextQuery.industries,
      });
      if (refresh) params.set("refresh", "1");
      const response = await fetch(`${API_BASE}/api/industry-data?${params.toString()}`, {
        signal: controller.signal,
      });
      const payload = (await response.json()) as IndustryDataResponse & { error?: string };
      if (!response.ok) throw new Error(payload.error || "行业数据接口请求失败");
      if (requestId !== requestIdRef.current) return;
      setIndustryData(payload);
      setStatus(payload.status === "partial" ? "部分数据已返回" : "数据已更新");
    } catch (fetchError) {
      if (requestId !== requestIdRef.current) return;
      const message =
        fetchError instanceof DOMException && fetchError.name === "AbortError"
          ? "请求超时，请确认后端服务是否可用"
          : fetchError instanceof Error
            ? fetchError.message
            : "行业数据加载失败";
      setError(message);
      setStatus("行业数据加载失败");
    } finally {
      window.clearTimeout(timeout);
      if (requestId === requestIdRef.current) {
        abortRef.current = null;
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadIndustryData(initialQuery.current, false);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AppShell active="industry">
      <SectionShell
        title="行业监控"
        description="直接展示行业指标最新值、上期变化和短期趋势，不做搜索入口。"
        meta={industryData?.fetchedAt ? new Date(industryData.fetchedAt).toLocaleString() : moduleText}
        action={
          <button
            type="button"
            className="query-button secondary-button"
            disabled={isLoading}
            onClick={() => void loadIndustryData(query, true)}
          >
            刷新数据
          </button>
        }
      >
        <div className="industry-monitor-summary">
          <div>
            <span>行业模块</span>
            <strong>{moduleText}</strong>
          </div>
          <div>
            <span>可读指标</span>
            <strong>{headlineMetrics.length}</strong>
          </div>
          <div>
            <span>状态</span>
            <strong>{status}</strong>
          </div>
        </div>
        {error ? <div className="error-box">{error}</div> : null}

        <div className="industry-switch-grid">
          {INDUSTRY_CHOICES.map((item) => (
            <button
              key={item.industries}
              type="button"
              className={`industry-switch-button ${query.industries === item.industries ? "active" : ""}`}
              disabled={isLoading}
              onClick={() => void loadIndustryData(item, false)}
            >
              <span>{item.label}</span>
              <small>{item.focus}</small>
            </button>
          ))}
        </div>

        {headlineMetrics.length ? (
          <div className="industry-monitor-grid">
            {headlineMetrics.map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </div>
        ) : null}
      </SectionShell>

      <IndustrySpecificPanel
        query={{ ...query, industries: selectedModuleKey }}
        modulePayload={industryData?.data?.[selectedModuleKey] ?? getNonferrousModule(industryData)}
        metrics={selectedMonitorMetrics}
      />


      <SectionShell
        title="原始数据明细"
        description="每个指标保留最近几条原始返回值，方便核对最新值来自哪一列。"
        meta={`${detailMetrics.length} 张表`}
      >
        <div className="industry-detail-table-grid">
          {detailMetrics.map((metric) => (
            <DetailTable key={metric.id} metric={metric} />
          ))}
        </div>

        {industryData?.errors && Object.keys(industryData.errors).length ? (
          <div className="revenue-section-card system-files-card">
            <h4>模块异常</h4>
            {Object.entries(industryData.errors).map(([moduleKey, message]) => (
              <div key={moduleKey} className="revenue-row">
                <div>
                  <div className="revenue-row-title">{MODULE_LABELS[moduleKey] || moduleKey}</div>
                  <div className="revenue-row-meta">{message}</div>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </SectionShell>
    </AppShell>
  );
}
