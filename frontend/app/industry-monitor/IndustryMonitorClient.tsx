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
  stock: string;
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
  stock: string;
  years: string;
  industries: string;
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

type ExtractedMetric = {
  id: string;
  moduleKey: string;
  moduleLabel: string;
  title: string;
  value: number | null;
  unit: string;
  sourceText: string;
};

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
  companyFinancialAbstract: "公司金融指标",
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
  if (typeof window === "undefined") return { stock: "600519", years: "8", industries: "auto" };
  const params = new URLSearchParams(window.location.search);
  return {
    stock: params.get("stock")?.trim() || "600519",
    years: params.get("years")?.trim() || "8",
    industries: params.get("industries")?.trim() || "auto",
  };
}

function formatNumber(value?: number | null, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
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

function isTablePreview(value: unknown): value is IndustryTablePreview {
  return Boolean(value && typeof value === "object" && "rows" in value && "columns" in value && "status" in value);
}

function isIndicatorGroup(value: unknown): value is IndustryIndicatorGroup {
  return Boolean(value && typeof value === "object" && "tables" in value && "source" in value);
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
      }
    });
  });
  return metrics;
}

function collectExtractedMetrics(industryData?: IndustryDataResponse | null) {
  const extracted: ExtractedMetric[] = [];
  Object.entries(industryData?.data ?? {}).forEach(([moduleKey, modulePayload]) => {
    const moduleLabel = MODULE_LABELS[moduleKey] || moduleKey;
    const reportMetrics = modulePayload.metrics?.reportExtractedMetrics;
    if (!reportMetrics || typeof reportMetrics !== "object") return;
    Object.entries(reportMetrics as Record<string, unknown>).forEach(([metricKey, value]) => {
      if (!Array.isArray(value)) return;
      value.slice(0, 3).forEach((item, index) => {
        if (!item || typeof item !== "object") return;
        const record = item as Record<string, unknown>;
        extracted.push({
          id: `${moduleKey}-${metricKey}-${index}`,
          moduleKey,
          moduleLabel,
          title: TABLE_LABELS[metricKey] || metricKey,
          value: typeof record.value === "number" ? record.value : null,
          unit: typeof record.unit === "string" ? record.unit : "",
          sourceText: typeof record.sourceText === "string" ? record.sourceText : "",
        });
      });
    });
  });
  return extracted;
}

function Sparkline({ points }: { points: MetricPoint[] }) {
  const values = points.map((point) => point.value).filter(Number.isFinite);
  if (values.length < 2) return <div className="industry-sparkline-empty">趋势不足</div>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const polyline = values
    .map((value, index) => {
      const x = values.length === 1 ? 0 : (index / (values.length - 1)) * 100;
      const y = 34 - ((value - min) / range) * 28;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg className="industry-sparkline" viewBox="0 0 100 40" role="img" aria-label="趋势图">
      <polyline points={polyline} fill="none" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      {values.map((value, index) => {
        const x = values.length === 1 ? 0 : (index / (values.length - 1)) * 100;
        const y = 34 - ((value - min) / range) * 28;
        return <circle key={`${value}-${index}`} cx={x} cy={y} r={index === values.length - 1 ? 3 : 1.8} />;
      })}
    </svg>
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

export default function IndustryMonitorClient() {
  const initialQuery = useRef(readQueryState());
  const [industryData, setIndustryData] = useState<IndustryDataResponse | null>(null);
  const [status, setStatus] = useState("正在加载行业数据");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  const monitorMetrics = useMemo(() => collectMonitorMetrics(industryData), [industryData]);
  const extractedMetrics = useMemo(() => collectExtractedMetrics(industryData), [industryData]);
  const headlineMetrics = monitorMetrics.filter((metric) => metric.value !== null).slice(0, 9);
  const detailMetrics = monitorMetrics.slice(0, 8);
  const activeModules = industryData?.industries ?? [];
  const moduleText = activeModules.map((item) => MODULE_LABELS[item] || item).join("、") || "自动识别";

  async function loadIndustryData(refresh = false) {
    abortRef.current?.abort();
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    setIsLoading(true);
    setStatus(refresh ? "正在刷新行业数据" : "正在加载行业数据");
    setError(null);

    try {
      const params = new URLSearchParams({
        stock: initialQuery.current.stock,
        years: initialQuery.current.years,
        industries: initialQuery.current.industries,
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
    void loadIndustryData(false);
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
            onClick={() => void loadIndustryData(true)}
          >
            刷新数据
          </button>
        }
      >
        <div className="industry-monitor-summary">
          <div>
            <span>监控对象</span>
            <strong>{initialQuery.current.stock}</strong>
          </div>
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

        <div className="industry-monitor-grid">
          {headlineMetrics.map((metric) => (
            <MetricCard key={metric.id} metric={metric} />
          ))}
          {!headlineMetrics.length ? (
            <div className="revenue-section-card revenue-section-card-wide">
              <h4>暂无可展示数值</h4>
              <div className="subtle">后端已返回数据时，会在这里展示最新值和趋势图。</div>
            </div>
          ) : null}
        </div>
      </SectionShell>

      {extractedMetrics.length ? (
        <SectionShell
          title="年报提取指标"
          description="从公司年报文本中抽取的经营指标，作为行业数据之外的公司口径补充。"
          meta={`${extractedMetrics.length} 条`}
        >
          <div className="industry-extracted-grid">
            {extractedMetrics.slice(0, 6).map((metric) => (
              <article key={metric.id} className="industry-extracted-card">
                <div className="industry-monitor-eyebrow">{metric.moduleLabel}</div>
                <h3>{metric.title}</h3>
                <div className="industry-monitor-value">
                  {formatNumber(metric.value, 2)}
                  {metric.unit ? <small>{metric.unit}</small> : null}
                </div>
                {metric.sourceText ? <p>{metric.sourceText}</p> : null}
              </article>
            ))}
          </div>
        </SectionShell>
      ) : null}

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
