"use client";

import { useEffect, useRef, useState } from "react";
import { AppShell, QueryBar, SectionShell } from "../components";

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
const API_BASE = configuredApiBase || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

type IndustryTablePreview = {
  status: "ok" | "empty" | "error" | string;
  columns: string[];
  rows: Array<Record<string, string | number | boolean | null>>;
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

type IndustryChoice = {
  value: string;
  label: string;
  hint: string;
};

const INDUSTRY_CHOICES: IndustryChoice[] = [
  { value: "auto", label: "自动识别", hint: "根据公司画像和主营构成选择模块" },
  { value: "baijiu", label: "白酒", hint: "销量、渠道、库存、价格带" },
  { value: "nonferrous_chemical", label: "有色/化工", hint: "商品价格、能源成本、产销披露" },
  { value: "shipping", label: "航运", hint: "运价指数、燃油、吞吐量" },
  { value: "financial", label: "金融", hint: "利率、社融、保险收入、公司金融指标" },
  { value: "game_internet", label: "游戏/互联网", hint: "用户、流水、版号和票房代理" },
  { value: "auto_new_energy", label: "汽车新能源", hint: "乘联会、出口、电池材料" },
];

const PRESET_STOCKS = [
  { code: "600519", label: "贵州茅台" },
  { code: "601600", label: "中国铝业" },
  { code: "601919", label: "中远海控" },
  { code: "002594", label: "比亚迪" },
  { code: "601288", label: "农业银行" },
  { code: "300052", label: "中青宝" },
];

const INDUSTRY_MODULE_LABELS: Record<string, string> = {
  baijiu: "白酒",
  nonferrous_chemical: "有色/化工",
  shipping: "航运",
  financial: "金融",
  game_internet: "游戏/互联网",
  auto_new_energy: "汽车新能源",
};

const INDICATOR_GROUPS = [
  {
    key: "macroOperatingIndicators",
    title: "宏观经营",
    description: "工业增加值、PMI、PPI、用电量和企业景气，判断行业需求温度。",
    tone: "demand",
  },
  {
    key: "customsTradeIndicators",
    title: "海关进出口",
    description: "出口、进口、贸易差额，辅助判断外需和进出口链条压力。",
    tone: "trade",
  },
  {
    key: "energyCostIndicators",
    title: "能源成本",
    description: "油价、能源库存、能源指数和碳市场，观察成本端和碳约束。",
    tone: "cost",
  },
];

const INDUSTRY_TABLE_LABELS: Record<string, string> = {
  industrialProductionYoy: "工业增加值同比",
  industrialValueAdded: "工业增加值",
  manufacturingPmi: "制造业 PMI",
  ppi: "PPI",
  electricityConsumption: "全社会用电",
  enterpriseBoomIndex: "企业景气",
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

function readQueryState() {
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

function formatIndustryCell(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isFinite(value) ? formatNumber(value, Math.abs(value) >= 100 ? 0 : 2) : "-";
  return String(value);
}

function isIndicatorGroup(value: unknown): value is IndustryIndicatorGroup {
  return Boolean(value && typeof value === "object" && "tables" in value && "source" in value);
}

function isTablePreview(value: unknown): value is IndustryTablePreview {
  return Boolean(value && typeof value === "object" && "rows" in value && "columns" in value && "status" in value);
}

function getRowPreview(row: Record<string, string | number | boolean | null>, columns: string[]) {
  const preferredColumns = columns.length ? columns : Object.keys(row);
  return preferredColumns.slice(0, 4).map((column) => ({
    column,
    value: formatIndustryCell(row[column]),
  }));
}

function summarizeTable(table?: IndustryTablePreview) {
  if (!table) return "未返回";
  if (table.status === "error") return table.error || "接口异常";
  if (table.status === "empty") return "暂无数据";
  const rowCount = table.rowCount ?? table.rows?.length ?? 0;
  return `${rowCount} 行`;
}

function collectCommonGroups(industryData?: IndustryDataResponse | null) {
  const modules = Object.entries(industryData?.data ?? {});
  return INDICATOR_GROUPS.map((group) => {
    const owner = modules.find(([, payload]) => isIndicatorGroup(payload.metrics?.[group.key]));
    const indicator = owner ? (owner[1].metrics?.[group.key] as IndustryIndicatorGroup) : null;
    return {
      ...group,
      moduleKey: owner?.[0] ?? "",
      moduleLabel: owner ? INDUSTRY_MODULE_LABELS[owner[0]] || owner[0] : "",
      indicator,
    };
  });
}

function collectSpecialTables(modulePayload?: IndustryModulePayload) {
  const metrics = modulePayload?.metrics ?? {};
  return Object.entries(metrics).filter(([, value]) => isTablePreview(value) || (value && typeof value === "object"));
}

function renderTableCard(tableKey: string, table: IndustryTablePreview) {
  return (
    <div key={tableKey} className="industry-table-card">
      <div className="industry-table-title">
        <span>{INDUSTRY_TABLE_LABELS[tableKey] || tableKey}</span>
        <em>{summarizeTable(table)}</em>
      </div>
      {table.rows?.slice(0, 3).map((row, rowIndex) => (
        <div key={`${tableKey}-${rowIndex}`} className="industry-row-preview">
          {getRowPreview(row, table.columns).map((item) => (
            <span key={`${tableKey}-${rowIndex}-${item.column}`}>
              <b>{item.column}</b>
              {item.value}
            </span>
          ))}
        </div>
      ))}
      {table.status === "error" ? <div className="industry-error-text">{table.error}</div> : null}
    </div>
  );
}

export default function IndustryMonitorClient() {
  const initialQuery = useRef(readQueryState());
  const [stock, setStock] = useState(initialQuery.current.stock);
  const [years, setYears] = useState(initialQuery.current.years);
  const [period, setPeriod] = useState("");
  const [industries, setIndustries] = useState(initialQuery.current.industries);
  const [industryData, setIndustryData] = useState<IndustryDataResponse | null>(null);
  const [status, setStatus] = useState("等待加载行业经营数据");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  const commonGroups = collectCommonGroups(industryData);
  const combinedError = error || "";
  const activeModules = industryData?.industries ?? [];
  const activeCompanyName = activeModules.length
    ? activeModules.map((item) => INDUSTRY_MODULE_LABELS[item] || item).join("、")
    : "";

  function syncUrl(nextStock: string, nextYears: string, nextIndustries: string) {
    const params = new URLSearchParams({ stock: nextStock, years: nextYears, industries: nextIndustries });
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }

  async function loadIndustryData(nextStock = stock, nextYears = years, nextIndustries = industries, refresh = false) {
    abortRef.current?.abort();
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    setIsLoading(true);
    setStatus("正在加载行业经营数据...");
    setError(null);
    setIndustryData(null);
    syncUrl(nextStock, nextYears, nextIndustries);

    try {
      const params = new URLSearchParams({
        stock: nextStock.trim() || "600519",
        years: nextYears.trim() || "8",
        industries: nextIndustries,
      });
      if (refresh) params.set("refresh", "1");
      const response = await fetch(`${API_BASE}/api/industry-data?${params.toString()}`, {
        signal: controller.signal,
      });
      const payload = (await response.json()) as IndustryDataResponse & { error?: string };
      if (!response.ok) throw new Error(payload.error || "行业经营数据接口请求失败");
      if (requestId !== requestIdRef.current) return;
      setIndustryData(payload);
      setStatus(payload.status === "partial" ? "部分行业数据已加载" : "行业经营数据已加载");
    } catch (fetchError) {
      if (requestId !== requestIdRef.current) return;
      const message =
        fetchError instanceof DOMException && fetchError.name === "AbortError"
          ? "请求超时，请确认后端服务是否可用"
          : fetchError instanceof Error
            ? fetchError.message
            : "行业经营数据加载失败";
      setError(message);
      setStatus("行业经营数据加载失败");
    } finally {
      window.clearTimeout(timeout);
      if (requestId === requestIdRef.current) {
        abortRef.current = null;
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadIndustryData(initialQuery.current.stock, initialQuery.current.years, initialQuery.current.industries);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AppShell active="industry">
      <QueryBar
        stock={stock}
        period={period}
        years={years}
        activeCompanyName={activeCompanyName}
        presets={PRESET_STOCKS}
        isLoading={isLoading}
        combinedError={combinedError}
        onStockChange={setStock}
        onPeriodChange={setPeriod}
        onYearsChange={setYears}
        onQuery={() => void loadIndustryData()}
        onPresetSelect={(presetStock) => {
          setStock(presetStock);
          void loadIndustryData(presetStock, years, industries);
        }}
      />

      <SectionShell
        title="行业监控"
        description="把公司主营业务、行业需求、进出口和成本变量放在同一个看板里，观察利润驱动是否顺风。"
        meta={industryData?.fetchedAt ? new Date(industryData.fetchedAt).toLocaleString() : "实时查询"}
        action={
          <button
            type="button"
            className="query-button secondary-button"
            disabled={isLoading}
            onClick={() => void loadIndustryData(stock, years, industries, true)}
          >
            强制刷新
          </button>
        }
      >
        <div className="status">{status}</div>

        <div className="industry-choice-grid">
          {INDUSTRY_CHOICES.map((item) => (
            <button
              key={item.value}
              type="button"
              className={`industry-choice-button ${industries === item.value ? "active" : ""}`}
              disabled={isLoading}
              onClick={() => {
                setIndustries(item.value);
                void loadIndustryData(stock, years, item.value);
              }}
            >
              <span>{item.label}</span>
              <small>{item.hint}</small>
            </button>
          ))}
        </div>

        <div className="industry-overview-grid">
          {commonGroups.map((group) => {
            const tables = Object.values(group.indicator?.tables ?? {});
            const okCount = tables.filter((table) => table.status === "ok").length;
            return (
              <div key={group.key} className={`mini-metric-card industry-kpi-card industry-group-${group.tone}`}>
                <div className="mini-metric-label">{group.title}</div>
                <div className="mini-metric-value">{group.indicator ? `${okCount}/${tables.length}` : "-"}</div>
                <div className="mini-metric-sub">
                  {group.indicator ? "可用表格" : "等待接口返回"}
                  {group.moduleLabel ? ` · ${group.moduleLabel}` : ""}
                </div>
              </div>
            );
          })}
        </div>

        <div className="industry-data-grid">
          {commonGroups.map((group) => {
            const tables = Object.entries(group.indicator?.tables ?? {});
            return (
              <div key={group.key} className={`revenue-section-card industry-group-card industry-group-${group.tone}`}>
                <div className="industry-group-header">
                  <div>
                    <h4>{group.title}</h4>
                    <div className="subtle">{group.description}</div>
                  </div>
                  <div className="industry-status-chip">{group.indicator?.status || "未加载"}</div>
                </div>
                <div className="industry-source-line">
                  {group.indicator?.source || "等待行业数据接口返回"}
                  {group.moduleLabel ? ` · 来自 ${group.moduleLabel} 模块` : ""}
                </div>
                {tables.length ? (
                  <div className="industry-table-grid">
                    {tables.map(([tableKey, table]) => renderTableCard(tableKey, table))}
                  </div>
                ) : (
                  <div className="subtle">这个数据包还没有可展示的表格。</div>
                )}
                {group.indicator?.dataGaps?.length ? (
                  <div className="industry-gap-line">{group.indicator.dataGaps.join("；")}</div>
                ) : null}
              </div>
            );
          })}
        </div>
      </SectionShell>

      <SectionShell
        title="行业专项数据"
        description="每个识别出的行业模块会追加自己的经营指标，例如商品价格、航运指数、汽车销量、金融利率或票房代理数据。"
        meta={activeModules.map((item) => INDUSTRY_MODULE_LABELS[item] || item).join("、") || "等待识别"}
      >
        <div className="industry-module-grid">
          {Object.entries(industryData?.data ?? {}).map(([moduleKey, modulePayload]) => {
            const metricEntries = collectSpecialTables(modulePayload);
            const commonKeys = new Set(INDICATOR_GROUPS.map((item) => item.key));
            const specialEntries = metricEntries.filter(([key]) => !commonKeys.has(key));
            return (
              <div key={moduleKey} className="revenue-section-card industry-module-card">
                <div className="industry-group-header">
                  <div>
                    <h4>{INDUSTRY_MODULE_LABELS[moduleKey] || moduleKey}</h4>
                    <div className="subtle">{modulePayload.source?.join("、") || "公开数据源"}</div>
                  </div>
                  <div className="industry-status-chip">{modulePayload.status}</div>
                </div>

                {specialEntries.length ? (
                  <div className="industry-table-grid">
                    {specialEntries.map(([metricKey, metricValue]) => {
                      if (isTablePreview(metricValue)) return renderTableCard(metricKey, metricValue);
                      if (metricValue && typeof metricValue === "object" && "tables" in metricValue) return null;
                      return (
                        <div key={metricKey} className="industry-table-card">
                          <div className="industry-table-title">
                            <span>{INDUSTRY_TABLE_LABELS[metricKey] || metricKey}</span>
                            <em>对象</em>
                          </div>
                          <pre className="industry-json-preview">
                            {JSON.stringify(metricValue, null, 2).slice(0, 900)}
                          </pre>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="subtle">该模块暂时只有通用宏观、海关或能源指标。</div>
                )}

                {modulePayload.dataGaps?.length ? (
                  <div className="industry-gap-line">{modulePayload.dataGaps.join("；")}</div>
                ) : null}
              </div>
            );
          })}
          {!industryData ? <div className="subtle">正在等待行业数据返回。</div> : null}
        </div>

        {industryData?.errors && Object.keys(industryData.errors).length ? (
          <div className="revenue-section-card system-files-card">
            <h4>模块异常</h4>
            {Object.entries(industryData.errors).map(([moduleKey, message]) => (
              <div key={moduleKey} className="revenue-row">
                <div>
                  <div className="revenue-row-title">{INDUSTRY_MODULE_LABELS[moduleKey] || moduleKey}</div>
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
