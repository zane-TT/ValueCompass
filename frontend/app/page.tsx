"use client";

import {
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
  type RefObject,
} from "react";
import * as echarts from "echarts";
import {
  AiAnalysisSection,
  AutoConclusionStrip,
  BusinessModelSection,
  ChartPanel,
  QueryBar,
  SystemStatus,
  type AutoConclusionItem,
} from "./components";

type BalanceResponse = {
  stock: string;
  title: string;
  reportDate: string;
  unit: string;
  treeData: {
    name: string;
    children: Array<{
      name: string;
      children: Array<{ name: string; value: number }>;
    }>;
  };
  barData: Array<{ name: string; value: number; type: "asset" | "liability" }>;
  conclusion: string;
};

type TrendResponse = {
  stock: string;
  title: string;
  unit: string;
  leftAxisName: string;
  rightAxisName: string;
  revenueBars: Array<{ date: string; value: number }>;
  marketCapLine: Array<{ date: string; value: number }>;
  conclusion: string;
};

type PeTrendResponse = {
  stock: string;
  title: string;
  unit: string;
  peLine: Array<{ date: string; value: number }>;
  meanLine: number;
  lowLine: number;
  highLine: number;
  conclusion: string;
};

type ProfitMarketCapResponse = {
  stock: string;
  title: string;
  unit: string;
  leftAxisName: string;
  rightAxisName: string;
  profitBars: Array<{ date: string; value: number }>;
  marketCapLine: Array<{ date: string; value: number }>;
  conclusion: string;
};

type CashFlowQualityResponse = {
  stock: string;
  title: string;
  unit: string;
  operatingCashFlow: Array<{ date: string; value: number }>;
  netProfit: Array<{ date: string; value: number }>;
  cashToProfitRatio: Array<{ date: string; value: number }>;
  conclusion: string;
};

type FinancialPoint = {
  date: string;
  value: number;
};

type RevenueBreakdownItem = {
  itemName: string;
  revenue: number;
  revenueRatio: number;
  cost?: number;
  grossMargin?: number;
  revenueGrowth?: number;
  grossMarginChangeText?: string;
  businessDescription?: string;
  priceDrivers?: string[];
};

type PositioningEvidenceItem = {
  type: string;
  label: string;
  detail: string;
};

type RevenueStructureResponse = {
  stock: string;
  companyName: string;
  industry: string;
  reportDate: string;
  analysisDimensionCoverage: {
    product: boolean;
    region: boolean;
    channel: boolean;
    industry: boolean;
    contractLiability: boolean;
  };
  businessSummary: {
    mainBusiness: string;
    interpretedMainBusiness?: string;
    companyIntro: string;
    trendConclusion: string;
  };
  companyPositioning: {
    companyNature: "service" | "product" | "platform";
    confidence?: number;
    primaryUnitLabel: string;
    rationale: string;
    evidence?: {
      supports: PositioningEvidenceItem[];
      conflicts: PositioningEvidenceItem[];
    };
    watchMetrics?: string[];
  };
  breakdowns: {
    byProduct: RevenueBreakdownItem[];
    byRegion: RevenueBreakdownItem[];
    byChannel: RevenueBreakdownItem[];
    byIndustry: RevenueBreakdownItem[];
  };
  highlights: {
    topProduct?: RevenueBreakdownItem & { isHighlyConcentrated?: boolean };
    topRegion?: RevenueBreakdownItem & { isHighlyConcentrated?: boolean };
    topChannel?: RevenueBreakdownItem & { isHighlyConcentrated?: boolean };
    bestGrossMarginProduct?: RevenueBreakdownItem;
    bestGrossMarginChannel?: RevenueBreakdownItem;
    contractLiability?: { name: string; value: number; type: "asset" | "liability" };
  };
  insightPoints: string[];
};

type AiAnalysisResponse = {
  stock: string;
  period: string;
  years: number;
  model: string;
  analysis: string;
  businessTypeAnalysis?: BusinessTypeAnalysisPayload | null;
};

type BusinessTypeAnalysisPayload = {
  company_name: string;
  business_type: string;
  company_nature?: "service" | "product" | "platform";
  evidence_strength?: "strong" | "medium" | "weak";
  confidence: number;
  main_revenue_source: string;
  main_profit_source: string;
  growth_driver: string;
  supports?: Array<{
    point: string;
    evidence: string;
  }>;
  conflicts?: Array<{
    point: string;
    evidence: string;
  }>;
  watch_metrics?: string[];
  uncertainty?: string;
  key_evidence: Array<{
    evidence_type: string;
    description: string;
  }>;
  why_this_type: string;
  not_other_types_reason: Array<{
    type: string;
    reason: string;
  }>;
  risks: string[];
  missing_data: string[];
  final_summary: string;
};

type BalanceHelp = {
  meaning: string;
  example: string;
  watch: string;
};

type QueryState = {
  stock: string;
  period: string;
  years: string;
};

type ChartId = "revenue" | "profit" | "cashflow" | "balance" | "pe";

type HealthResponse = {
  status: string;
  service: string;
  startedAt: string;
  now: string;
  uptimeSeconds: number;
  pythonVersion: string;
  cache: {
    directory: string;
    exists: boolean;
    fileCount: number;
    totalBytes: number;
  };
};

type CacheStatsResponse = {
  status: string;
  cache: {
    directory: string;
    exists: boolean;
    fileCount: number;
    totalBytes: number;
  };
  recentFiles: Array<{
    name: string;
    sizeBytes: number;
    modifiedAt: string;
  }>;
};

type PeerCompaniesResponse = {
  stock: string;
  companyName: string;
  industry: string;
  source: string;
  sourceLabel: string;
  peers: Array<{
    stock: string;
    name: string;
    score: number;
    reasons: string[];
    source: string;
  }>;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:5001" : "");

const CHART_OPTIONS: Array<{ id: ChartId; label: string; description: string }> = [
  { id: "revenue", label: "营收与市值", description: "收入规模和市值走势" },
  { id: "profit", label: "净利润与市值", description: "盈利能力和市场定价" },
  { id: "cashflow", label: "现金流与盈利质量", description: "利润是否转化为现金" },
  { id: "balance", label: "资产负债结构", description: "资产和负债构成" },
  { id: "pe", label: "市盈率趋势", description: "估值所处区间" },
];

const BALANCE_TERM_HELP: Record<string, BalanceHelp> = {
  "asset:现金": {
    meaning: "公司手里最容易动用的钱，流动性最强，通常包括货币资金和其他货币资金。",
    example: "银行存款、库存现金、保证金、受限资金等。",
    watch: "现金多通常说明安全垫较厚，但也要看是否受限；如果账上现金很多，同时还有大量有息负债，要继续看公司是否存在资金使用效率低或资金受限的问题。",
  },
  "asset:应收款": {
    meaning: "公司已经确认收入，但客户还没有真正把钱付过来。它代表未来可能收到的钱，但也可能收不回来。",
    example: "应收账款、应收票据、应收款项融资、客户赊账款。",
    watch: "应收款增长太快要警惕，尤其是应收款增速明显高于收入增速时，可能说明公司回款变慢，收入质量下降。好公司通常更希望卖货后尽快收现金。",
  },
  "asset:预付款": {
    meaning: "公司提前付给供应商的钱，未来会换成商品、原材料或服务。",
    example: "预付采购款、预付原材料款、预付广告费、预付工程款。",
    watch: "预付款太高，说明公司在产业链里议价能力可能较弱，需要先给别人钱。如果预付款长期异常增加，要看是不是和关联方交易、采购真实性有关。",
  },
  "asset:存货": {
    meaning: "公司还没有卖出去的商品、原材料、半成品或在产品。存货最终要通过销售变成收入和现金。",
    example: "白酒库存、家电库存、原材料、半成品、在产品、库存商品。",
    watch: "存货不是越多越好。存货多可能代表未来可卖的货，也可能代表卖不动、积压或跌价风险。要结合行业看，比如白酒存货和电子产品存货的风险完全不同。",
  },
  "asset:其他流动": {
    meaning: "一年内可能变现或消耗掉的其他资产，但不属于现金、应收款、存货等主要项目。",
    example: "短期理财、待抵扣税费、其他应收款、合同资产、待摊费用。",
    watch: "这个科目比较杂，金额太大时要拆开看明细。财报分析里，越是名字叫“其他”的项目，越不能只看总数，因为里面可能藏着重要信息。",
  },
  "asset:长期投资": {
    meaning: "公司长期持有的对外投资，通常不是为了短期买卖，而是为了战略布局、参股、控股或长期收益。",
    example: "长期股权投资、参股公司股权、其他权益工具投资、其他非流动金融资产。",
    watch: "长期投资要看投的是什么公司，能不能带来利润。如果长期投资金额很大，但投资收益很少，说明资金占用效率可能不高。",
  },
  "asset:固定资产": {
    meaning: "公司长期使用的实物资产，不是用来直接卖的，而是用来生产、经营、办公。",
    example: "厂房、机器设备、生产线、车辆、办公楼、仓库。",
    watch: "固定资产重的公司通常资本开支大、折旧压力大，比如制造业、能源、交通运输。固定资产少的公司通常更轻资产，比如互联网、软件服务。要结合行业判断。",
  },
  "asset:无形&商誉": {
    meaning: "无形资产是没有实体形态但有价值的资产；商誉通常来自并购，代表收购价格超过被收购公司净资产公允价值的部分。",
    example: "商标、专利、软件、土地使用权、版权、客户资源、并购形成的商誉。",
    watch: "商誉要特别关注减值风险。公司高价收购后，如果被收购公司业绩不达预期，商誉可能减值，直接影响利润。",
  },
  "asset:其他固定": {
    meaning: "其他不容易在一年内变现的长期资产，通常属于非流动资产里的杂项。",
    example: "长期待摊费用、递延所得税资产、其他非流动资产、在建工程相关款项。",
    watch: "金额不大通常问题不大；如果金额很大，要看附注明细。非流动资产变现慢，一旦质量不好，短期内不容易变成现金。",
  },
  "liability:短期借款": {
    meaning: "公司一年内需要偿还的银行借款或短期融资，属于短期有息负债。",
    example: "短期银行贷款、信用借款、抵押借款、保证借款。",
    watch: "短期借款高，说明公司短期还款压力大。要和现金一起看：如果现金覆盖不了短期借款，就要关注流动性风险。",
  },
  "liability:应付款": {
    meaning: "公司买了商品、原材料或服务，但还没有付给供应商的钱。",
    example: "应付账款、应付票据、采购欠款、供应商货款。",
    watch: "应付款多不一定坏。强势公司可以先拿货后付款，占用供应商资金，说明产业链地位强。但如果应付款异常增加，也可能说明公司资金紧张、拖欠供应商。",
  },
  "liability:预收款": {
    meaning: "客户已经提前付款，但公司还没有交货或还没有完成服务。新准则下很多会体现在合同负债。",
    example: "预收货款、合同负债、会员充值、客户订金。",
    watch: "预收款通常是好科目，说明客户愿意先付钱，公司议价能力强。比如品牌强、产品紧俏的公司，往往能先收钱再交货。",
  },
  "liability:薪酬&税": {
    meaning: "公司已经发生但还没有支付的员工薪酬，以及还没有缴纳的税费。",
    example: "应付工资、奖金、社保、公积金、企业所得税、增值税、消费税。",
    watch: "这个科目短期波动正常。年底奖金、税费结算会影响金额。如果长期异常偏高，要看是不是存在拖欠工资或税费压力。",
  },
  "liability:其他流动": {
    meaning: "一年内需要偿还或结转的其他负债，但不属于短期借款、应付款、税费等主要项目。",
    example: "其他应付款、一年内到期的非流动负债、待转销项税、短期应付费用。",
    watch: "这个科目也比较杂，金额大时必须看明细。特别要关注其他应付款里是否有大额关联方往来、押金保证金、拆借款。",
  },
  "liability:长期借款": {
    meaning: "偿还期限超过一年的借款，属于长期有息负债。",
    example: "长期银行贷款、项目贷款、抵押贷款、长期信用借款。",
    watch: "长期借款压力比短期借款缓和，但仍然要付利息。要结合经营现金流看公司能不能长期稳定覆盖利息和本金。",
  },
  "liability:其他非流动": {
    meaning: "一年以后才需要偿还或结转的其他长期负债。",
    example: "递延收益、递延所得税负债、长期应付款、租赁负债、预计负债。",
    watch: "非流动负债短期压力较小，但不代表不用还。金额大时要看期限、利率、是否有担保，以及未来是否会影响利润或现金流。",
  },
};

function formatBalanceTooltip(params: unknown) {
  const firstParam = Array.isArray(params) ? params[0] : params;

  const item = firstParam as {
    name?: string;
    marker?: string;
    data?: {
      value?: number;
      help?: BalanceHelp;
    };
  };

  const name = item.name ?? "";
  const value = item.data?.value ?? "-";
  const help = item.data?.help;

  return `
    <div style="width: 360px; max-width: 360px; white-space: normal; word-break: break-word; overflow-wrap: break-word; line-height: 1.7; font-size: 13px; color: #172033;">
      <div style="font-weight: 700; font-size: 15px; margin-bottom: 8px; color: #172033;">${name}</div>
      <div style="margin-bottom: 8px;">${item.marker ?? ""}<b>金额：</b>${value} 亿元</div>
      <div style="margin-bottom: 8px;"><div style="font-weight: 700; margin-bottom: 2px;">是什么：</div><div>${help?.meaning ?? "暂无说明"}</div></div>
      <div style="margin-bottom: 8px;"><div style="font-weight: 700; margin-bottom: 2px;">常见例子：</div><div>${help?.example ?? "暂无举例"}</div></div>
      <div><div style="font-weight: 700; margin-bottom: 2px;">怎么看：</div><div>${help?.watch ?? "暂无分析提示"}</div></div>
    </div>
  `;
}

function formatBalanceTooltipWithRatio(params: unknown) {
  const items = (Array.isArray(params) ? params : [params]) as Array<{
    name?: string;
    marker?: string;
    data?: {
      value?: number;
      amount?: number;
      ratioLabel?: string;
      groupLabel?: string;
      help?: BalanceHelp;
    };
  }>;

  const item =
    items.find((entry) => entry.data?.amount !== undefined || entry.data?.help) ?? items[0];

  const name = item.name ?? "";
  const amount = item.data?.amount ?? item.data?.value ?? "-";
  const ratioLabel = item.data?.ratioLabel ?? "-";
  const groupLabel = item.data?.groupLabel ?? "总额";
  const help = item.data?.help;

  return `
    <div style="width: 360px; max-width: 360px; white-space: normal; word-break: break-word; overflow-wrap: break-word; line-height: 1.7; font-size: 13px; color: #172033;">
      <div style="font-weight: 700; font-size: 15px; margin-bottom: 8px; color: #172033;">${name}</div>
      <div style="margin-bottom: 8px;">${item.marker ?? ""}<b>金额：</b>${amount} 亿元</div>
      <div style="margin-bottom: 8px;"><b>占${groupLabel}比：</b>${ratioLabel}</div>
      <div style="margin-bottom: 8px;"><div style="font-weight: 700; margin-bottom: 2px;">是什么：</div><div>${help?.meaning ?? "暂无说明"}</div></div>
      <div style="margin-bottom: 8px;"><div style="font-weight: 700; margin-bottom: 2px;">常见例子：</div><div>${help?.example ?? "暂无举例"}</div></div>
      <div><div style="font-weight: 700; margin-bottom: 2px;">怎么看：</div><div>${help?.watch ?? "暂无分析提示"}</div></div>
    </div>
  `;
}

function formatPercent(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function formatYiValue(value: number) {
  return `${value.toFixed(2)} 亿元`;
}

function formatYiChange(value: number) {
  if (Math.abs(value) < 0.01) return "基本持平";
  return `${value > 0 ? "增加" : "减少"} ${Math.abs(value).toFixed(2)} 亿元`;
}

function getYearEndPoints(points: FinancialPoint[]) {
  const byYear = new Map<string, FinancialPoint>();

  points
    .filter((item) => Number.isFinite(item.value) && !Number.isNaN(Date.parse(item.date)))
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date))
    .forEach((item) => {
      const year = new Date(item.date).getFullYear().toString();
      byYear.set(year, item);
    });

  return Array.from(byYear.entries()).map(([year, point]) => ({ year, ...point }));
}

function getProfitStatus(value: number) {
  if (value > 0) return "赚钱";
  if (value < 0) return "亏钱";
  return "盈亏平衡";
}

function buildPerformanceInsightPoints(
  profitData?: ProfitMarketCapResponse | null,
  trendData?: TrendResponse | null
) {
  const profitByYear = getYearEndPoints(profitData?.profitBars ?? []);
  const revenueByYear = getYearEndPoints(trendData?.revenueBars ?? []);
  const insights: string[] = [];

  if (profitByYear.length) {
    const recentProfit = profitByYear.slice(-4);
    const latest = recentProfit[recentProfit.length - 1];
    const profitableYears = recentProfit.filter((item) => item.value > 0).length;
    const lossYears = recentProfit.filter((item) => item.value < 0).length;
    const status = getProfitStatus(latest.value);
    const periodLabel = latest.date.slice(5, 10) === "12-31" ? `${latest.year} 年` : `${latest.year} 年截至 ${latest.date.slice(5)}`;

    insights.push(
      `盈利状态：${periodLabel}归母净利润为 ${formatYiValue(latest.value)}，公司最近一个报告期是${status}的。最近 ${recentProfit.length} 年中，${profitableYears} 年盈利、${lossYears} 年亏损。`
    );

    if (recentProfit.length >= 2) {
      const first = recentProfit[0];
      const change = latest.value - first.value;
      const trend =
        Math.abs(change) < 0.01
          ? "整体基本持平"
          : change > 0
            ? "整体改善"
            : "整体走弱";
      const profitSeries = recentProfit
        .map((item) => `${item.year} 年 ${formatYiValue(item.value)}`)
        .join("、");

      insights.push(
        `净利润趋势：最近几年归母净利润分别为 ${profitSeries}，从 ${first.year} 年到 ${latest.year} 年${formatYiChange(change)}，${trend}。`
      );
    }
  }

  if (revenueByYear.length >= 2) {
    const recentRevenue = revenueByYear.slice(-4);
    const first = recentRevenue[0];
    const latest = recentRevenue[recentRevenue.length - 1];
    const change = latest.value - first.value;
    const trend =
      Math.abs(change) < 0.01 ? "规模基本稳定" : change > 0 ? "收入规模在扩大" : "收入规模在收缩";

    insights.push(
      `营收趋势：${first.year} 年营业收入为 ${formatYiValue(first.value)}，${latest.year} 年为 ${formatYiValue(latest.value)}，${formatYiChange(change)}，${trend}。`
    );
  }

  return insights;
}

function buildAutoConclusionItems(
  profitData?: ProfitMarketCapResponse | null,
  trendData?: TrendResponse | null,
  revenueStructureData?: RevenueStructureResponse | null,
  cashFlowData?: CashFlowQualityResponse | null
): AutoConclusionItem[] {
  const profitByYear = getYearEndPoints(profitData?.profitBars ?? []);
  const revenueByYear = getYearEndPoints(trendData?.revenueBars ?? []);
  const cashRatioByYear = getYearEndPoints(cashFlowData?.cashToProfitRatio ?? []);
  const latestProfit = profitByYear.at(-1);
  const firstProfit = profitByYear.length >= 2 ? profitByYear[0] : null;
  const latestRevenue = revenueByYear.at(-1);
  const firstRevenue = revenueByYear.length >= 2 ? revenueByYear[0] : null;
  const latestCashRatio = cashRatioByYear.at(-1);

  const profitChange = latestProfit && firstProfit ? latestProfit.value - firstProfit.value : null;
  const revenueChange = latestRevenue && firstRevenue ? latestRevenue.value - firstRevenue.value : null;
  const topProductRatio = revenueStructureData?.highlights.topProduct?.revenueRatio;

  const profitTone =
    latestProfit && latestProfit.value < 0 ? "danger" : latestProfit && latestProfit.value > 0 ? "positive" : "neutral";
  const profitTrendTone =
    profitChange === null ? "neutral" : profitChange < 0 ? "warning" : profitChange > 0 ? "positive" : "neutral";
  const revenueTrendTone =
    revenueChange === null ? "neutral" : revenueChange < 0 ? "warning" : revenueChange > 0 ? "positive" : "neutral";
  const cashQualityTone =
    latestCashRatio === undefined
      ? "neutral"
      : latestCashRatio.value >= 1
        ? "positive"
        : latestCashRatio.value >= 0.5
          ? "warning"
          : "danger";
  const riskTone =
    latestProfit?.value !== undefined && latestProfit.value < 0
      ? "danger"
      : profitChange !== null && profitChange < 0
        ? "warning"
        : topProductRatio !== undefined && topProductRatio > 0.7
          ? "warning"
          : "positive";

  return [
    {
      label: "盈利状态",
      value: latestProfit ? getProfitStatus(latestProfit.value) : "待加载",
      detail: latestProfit ? `${latestProfit.year}：${formatYiValue(latestProfit.value)}` : "等待净利润数据",
      tone: profitTone,
    },
    {
      label: "净利润趋势",
      value: profitChange === null ? "样本不足" : profitChange >= 0 ? "改善" : "走弱",
      detail: profitChange === null ? "至少需要两年数据" : `${firstProfit?.year}-${latestProfit?.year} ${formatYiChange(profitChange)}`,
      tone: profitTrendTone,
    },
    {
      label: "营收趋势",
      value: revenueChange === null ? "样本不足" : revenueChange >= 0 ? "扩大" : "收缩",
      detail: revenueChange === null ? "至少需要两年数据" : `${firstRevenue?.year}-${latestRevenue?.year} ${formatYiChange(revenueChange)}`,
      tone: revenueTrendTone,
    },
    {
      label: "利润质量",
      value: latestCashRatio === undefined ? "待加载" : latestCashRatio.value >= 1 ? "好" : latestCashRatio.value >= 0.5 ? "一般" : "有压力",
      detail:
        latestCashRatio === undefined
          ? "等待现金流数据"
          : `${latestCashRatio.year} 净现比 ${latestCashRatio.value.toFixed(2)} 倍`,
      tone: cashQualityTone,
    },
    {
      label: "风险提示",
      value:
        latestProfit?.value !== undefined && latestProfit.value < 0
          ? "亏损风险"
          : profitChange !== null && profitChange < 0
            ? "利润承压"
            : topProductRatio !== undefined && topProductRatio > 0.7
              ? "业务集中"
              : "未见高危",
      detail:
        topProductRatio !== undefined && topProductRatio > 0.7
          ? `第一大业务占比 ${formatPercent(topProductRatio)}`
          : latestProfit
            ? `最近报告期 ${latestProfit.year}`
            : "等待更多样本",
      tone: riskTone,
    },
  ];
}

function formatCombinedStatus(statuses: string[]) {
  const finishedCount = statuses.filter((item) => item.includes("加载完成")).length;
  if (finishedCount === statuses.length) {
    return "数据已更新：资产负债、业绩趋势、市盈率、净利润、现金流与收入结构均已加载。";
  }

  return statuses.join(" | ");
}

function getCompanyNatureLabel(companyNature?: RevenueStructureResponse["companyPositioning"]["companyNature"]) {
  if (companyNature === "product") return "产品型";
  if (companyNature === "platform") return "平台型";
  return "服务型";
}

function normalizeAiCompanyNature(value?: string) {
  const text = String(value || "").toLowerCase();
  if (text.includes("平台") || text.includes("platform")) return "platform" as const;
  if (text.includes("产品") || text.includes("product")) return "product" as const;
  return "service" as const;
}

function formatConfidence(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatBytes(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatUptime(seconds?: number) {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) return "-";
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`;
  return `${(seconds / 3600).toFixed(1)} 小时`;
}

function mapAiBusinessTypeToPositioning(aiData?: BusinessTypeAnalysisPayload | null) {
  if (!aiData) return null;

  const companyNature = aiData.company_nature || normalizeAiCompanyNature(aiData.business_type);
  const supports =
    aiData.supports?.filter((item) => item.point || item.evidence).map((item) => ({
      type: "ai_support",
      label: item.point || "支持证据",
      detail: item.evidence || "",
    })) ||
    aiData.key_evidence
      ?.filter((item) => item.description)
      .map((item) => ({
        type: "ai_support",
        label: item.evidence_type || "关键证据",
        detail: item.description,
      })) ||
    [];

  const conflicts =
    aiData.conflicts?.filter((item) => item.point || item.evidence).map((item) => ({
      type: "ai_conflict",
      label: item.point || "反向证据",
      detail: item.evidence || "",
    })) ||
    aiData.not_other_types_reason
      ?.filter((item) => item.reason)
      .map((item) => ({
        type: "ai_conflict",
        label: item.type || "反向证据",
        detail: item.reason,
      })) ||
    [];

  return {
    source: "ai" as const,
    companyNature,
    confidence: aiData.confidence,
    primaryUnitLabel: companyNature === "platform" ? "平台业务" : companyNature === "product" ? "产品" : "业务",
    rationale: aiData.why_this_type || aiData.final_summary || "",
    evidence: {
      supports,
      conflicts,
    },
    watchMetrics: aiData.watch_metrics?.length
      ? aiData.watch_metrics
      : companyNature === "platform"
        ? ["GMV", "抽佣率", "商家数", "活跃用户", "广告/服务费变现"]
        : companyNature === "product"
          ? ["销量", "单价", "毛利率", "存货周转", "渠道结构"]
          : ["订单量", "履约能力", "利用率", "单位服务价格", "回款效率"],
    evidenceStrength: aiData.evidence_strength,
    uncertainty: aiData.uncertainty,
  };
}

function renderBreakdownRows(items: RevenueBreakdownItem[]) {
  return items.slice(0, 4).map((item) => (
    <div key={item.itemName} className="revenue-row">
      <div>
        <div className="revenue-row-title">{item.itemName}</div>
        <div className="revenue-row-meta">
          收入 {item.revenue} 亿 | 占比 {formatPercent(item.revenueRatio)}
        </div>
        {item.businessDescription ? (
          <div className="revenue-row-description">{item.businessDescription}</div>
        ) : null}
        {item.priceDrivers?.length ? (
          <div className="revenue-row-drivers">价格影响因素：{item.priceDrivers.join("、")}</div>
        ) : null}
      </div>
      <div className="revenue-row-side">
        <div>毛利率 {formatPercent(item.grossMargin)}</div>
        {item.revenueGrowth !== undefined ? <div>增速 {formatPercent(item.revenueGrowth)}</div> : null}
      </div>
    </div>
  ));
}

function readQueryState(searchParams: URLSearchParams): QueryState {
  return {
    stock: searchParams.get("stock")?.trim() || "600519",
    period: searchParams.get("period")?.trim() || "",
    years: searchParams.get("years")?.trim() || "8",
  };
}

export default function HomePage() {
  const [stock, setStock] = useState("600519");
  const [period, setPeriod] = useState("");
  const [years, setYears] = useState("8");
  const [selectedCharts, setSelectedCharts] = useState<ChartId[]>(["revenue", "profit", "cashflow", "pe"]);

  const [balanceStatus, setBalanceStatus] = useState("正在加载资产负债数据...");
  const [trendStatus, setTrendStatus] = useState("正在加载业绩与市值数据...");
  const [peStatus, setPeStatus] = useState("正在加载市盈率数据...");
  const [profitStatus, setProfitStatus] = useState("正在加载净利润与市值数据...");
  const [cashFlowStatus, setCashFlowStatus] = useState("正在加载现金流质量数据...");
  const [revenueStructureStatus, setRevenueStructureStatus] = useState("正在加载收入结构拆解...");
  const [peerStatus, setPeerStatus] = useState("正在识别同行竞品...");

  const [aiStatus, setAiStatus] = useState("点击“生成 AI 分析”获取综合解读");

  const [balanceError, setBalanceError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [peError, setPeError] = useState<string | null>(null);
  const [profitError, setProfitError] = useState<string | null>(null);
  const [cashFlowError, setCashFlowError] = useState<string | null>(null);
  const [revenueStructureError, setRevenueStructureError] = useState<string | null>(null);
  const [peerError, setPeerError] = useState<string | null>(null);

  const [aiError, setAiError] = useState<string | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [balanceData, setBalanceData] = useState<BalanceResponse | null>(null);
  const [trendData, setTrendData] = useState<TrendResponse | null>(null);
  const [peData, setPeData] = useState<PeTrendResponse | null>(null);
  const [profitData, setProfitData] = useState<ProfitMarketCapResponse | null>(null);
  const [cashFlowData, setCashFlowData] = useState<CashFlowQualityResponse | null>(null);
  const [revenueStructureData, setRevenueStructureData] = useState<RevenueStructureResponse | null>(null);
  const [peerData, setPeerData] = useState<PeerCompaniesResponse | null>(null);
  const [aiData, setAiData] = useState<AiAnalysisResponse | null>(null);
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [cacheStats, setCacheStats] = useState<CacheStatsResponse | null>(null);
  const aiPositioning = mapAiBusinessTypeToPositioning(aiData?.businessTypeAnalysis);
  const displayedPositioning = aiPositioning || revenueStructureData?.companyPositioning || null;
  const primaryUnitLabel = displayedPositioning?.primaryUnitLabel || "业务";
  const companyNatureLabel = getCompanyNatureLabel(displayedPositioning?.companyNature);
  const supportEvidence = displayedPositioning?.evidence?.supports ?? [];
  const conflictEvidence = displayedPositioning?.evidence?.conflicts ?? [];
  const watchMetrics = displayedPositioning?.watchMetrics ?? [];
  const autoConclusionItems = buildAutoConclusionItems(profitData, trendData, revenueStructureData, cashFlowData);

  const balanceChartRef = useRef<HTMLDivElement | null>(null);
  const trendChartRef = useRef<HTMLDivElement | null>(null);
  const peChartRef = useRef<HTMLDivElement | null>(null);
  const profitChartRef = useRef<HTMLDivElement | null>(null);
  const cashFlowChartRef = useRef<HTMLDivElement | null>(null);

  const balanceChart = useRef<echarts.ECharts | null>(null);
  const trendChart = useRef<echarts.ECharts | null>(null);
  const peChart = useRef<echarts.ECharts | null>(null);
  const profitChart = useRef<echarts.ECharts | null>(null);
  const cashFlowChart = useRef<echarts.ECharts | null>(null);

  function ensureChart(
    ref: RefObject<HTMLDivElement | null>,
    instanceRef: MutableRefObject<echarts.ECharts | null>
  ) {
    if (!ref.current) return;
    instanceRef.current = echarts.getInstanceByDom(ref.current) ?? echarts.init(ref.current);
  }

  function getQueryState(overrides?: Partial<QueryState>): QueryState {
    return {
      stock: (overrides?.stock ?? stock).trim() || "600519",
      period: (overrides?.period ?? period).trim(),
      years: (overrides?.years ?? years).trim() || "8",
    };
  }

  function syncUrl(query: QueryState) {
    const params = new URLSearchParams();
    params.set("stock", query.stock);
    params.set("years", query.years);
    if (query.period) params.set("period", query.period);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }

  useEffect(() => {
    ensureChart(balanceChartRef, balanceChart);
    ensureChart(trendChartRef, trendChart);
    ensureChart(peChartRef, peChart);
    ensureChart(profitChartRef, profitChart);
    ensureChart(cashFlowChartRef, cashFlowChart);

    const handleResize = () => {
      balanceChart.current?.resize();
      trendChart.current?.resize();
      peChart.current?.resize();
      profitChart.current?.resize();
      cashFlowChart.current?.resize();
    };

    window.addEventListener("resize", handleResize);
    requestAnimationFrame(handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      balanceChart.current?.dispose();
      trendChart.current?.dispose();
      peChart.current?.dispose();
      profitChart.current?.dispose();
      cashFlowChart.current?.dispose();
    };
  }, []);

  useEffect(() => {
    const initialQuery = readQueryState(new URLSearchParams(window.location.search));
    setStock(initialQuery.stock);
    setPeriod(initialQuery.period);
    setYears(initialQuery.years);
    void loadAllData(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedCharts.includes("balance")) {
      balanceChart.current?.dispose();
      balanceChart.current = null;
    }
    if (!selectedCharts.includes("revenue")) {
      trendChart.current?.dispose();
      trendChart.current = null;
    }
    if (!selectedCharts.includes("pe")) {
      peChart.current?.dispose();
      peChart.current = null;
    }
    if (!selectedCharts.includes("profit")) {
      profitChart.current?.dispose();
      profitChart.current = null;
    }
    if (!selectedCharts.includes("cashflow")) {
      cashFlowChart.current?.dispose();
      cashFlowChart.current = null;
    }

    if (selectedCharts.includes("balance")) ensureChart(balanceChartRef, balanceChart);
    if (selectedCharts.includes("revenue")) ensureChart(trendChartRef, trendChart);
    if (selectedCharts.includes("pe")) ensureChart(peChartRef, peChart);
    if (selectedCharts.includes("profit")) ensureChart(profitChartRef, profitChart);
    if (selectedCharts.includes("cashflow")) ensureChart(cashFlowChartRef, cashFlowChart);

    requestAnimationFrame(() => {
      balanceChart.current?.resize();
      trendChart.current?.resize();
      peChart.current?.resize();
      profitChart.current?.resize();
      cashFlowChart.current?.resize();
    });
  }, [selectedCharts]);

  useEffect(() => {
    if (!balanceData || !balanceChart.current) return;

    const totalAssets = balanceData.barData.reduce((sum, item) => {
      return item.type === "asset" ? sum + item.value : sum;
    }, 0);

    const seriesData = balanceData.barData.map((item) => {
      const ratio = totalAssets > 0 ? (item.value / totalAssets) * 100 : 0;

      return {
        name: item.name,
        value: Number(ratio.toFixed(2)),
        amount: item.value,
        ratioLabel: `${ratio.toFixed(1)}%`,
        help: BALANCE_TERM_HELP[`${item.type}:${item.name}`],
        groupLabel: "总资产",
        itemStyle: {
          color: item.type === "asset" ? "#4e79ff" : "#e05555",
        },
      };
    });

    balanceChart.current.clear();
    balanceChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          formatter: formatBalanceTooltipWithRatio,
          confine: true,
          extraCssText: `
            white-space: normal;
            max-width: 380px;
            border-radius: 8px;
            padding: 12px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
          `,
        },
        grid: { top: 24, left: 76, right: 96, bottom: 24, containLabel: true },
        xAxis: {
          type: "value",
          name: "占比",
          min: 0,
          max: 100,
          axisLabel: {
            formatter: (value: number) => `${value}%`,
          },
          splitLine: { lineStyle: { color: "#e8edf5" } },
        },
        yAxis: {
          type: "category",
          data: balanceData.barData.map((item) => item.name),
          axisLabel: { margin: 4 },
        },
        series: [
          {
            type: "bar",
            silent: true,
            barGap: "-100%",
            barWidth: 18,
            itemStyle: {
              color: "#eef3fb",
              borderRadius: [0, 6, 6, 0],
            },
            data: balanceData.barData.map(() => 100),
          },
          {
            type: "bar",
            barWidth: 18,
            itemStyle: {
              borderRadius: [0, 6, 6, 0],
            },
            label: {
              show: true,
              position: "right",
              color: "#334155",
              formatter: (params: { data?: { amount?: number; ratioLabel?: string } }) => {
                const amount = params.data?.amount ?? 0;
                const ratioLabel = params.data?.ratioLabel ?? "0.0%";
                return `${amount}亿  ${ratioLabel}`;
              },
            },
            data: seriesData,
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => balanceChart.current?.resize());
  }, [balanceData, selectedCharts]);

  useEffect(() => {
    if (!trendData || !trendChart.current) return;

    const allDates = [...trendData.revenueBars, ...trendData.marketCapLine]
      .map((item) => new Date(item.date).getTime())
      .filter((value) => Number.isFinite(value))
      .sort((left, right) => left - right);

    const xMin = allDates[0];
    const xMax = allDates[allDates.length - 1];

    trendChart.current.clear();
    trendChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: { trigger: "axis" },
        legend: { top: 8, data: ["营业总收入", "总市值"] },
        grid: { top: 56, left: 64, right: 28, bottom: 44, containLabel: true },
        xAxis: {
          type: "time",
          min: Number.isFinite(xMin) ? xMin : undefined,
          max: Number.isFinite(xMax) ? xMax : undefined,
          boundaryGap: false,
          axisLabel: {
            hideOverlap: true,
            formatter(value: number) {
              return echarts.time.format(value, "{yyyy}", false);
            },
          },
        },
        yAxis: [
          {
            type: "value",
            name: trendData.leftAxisName,
            axisLabel: { color: "#3f5fe8" },
            nameTextStyle: { color: "#3f5fe8" },
            splitLine: { lineStyle: { color: "#e8edf5" } },
          },
          {
            type: "value",
            name: trendData.rightAxisName,
            axisLabel: { color: "#e05555" },
            nameTextStyle: { color: "#e05555" },
            axisLine: { show: true, lineStyle: { color: "#e05555" } },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: "营业总收入",
            type: "bar",
            yAxisIndex: 0,
            barMaxWidth: 22,
            label: { show: false },
            itemStyle: { color: "#4e79ff" },
            data: trendData.revenueBars.map((item) => [item.date, item.value]),
          },
          {
            name: "总市值",
            type: "line",
            yAxisIndex: 1,
            showSymbol: false,
            smooth: true,
            label: { show: false },
            itemStyle: { color: "#e05555" },
            lineStyle: { color: "#e05555", width: 2 },
            data: trendData.marketCapLine.map((item) => [item.date, item.value]),
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => trendChart.current?.resize());
  }, [trendData, selectedCharts]);

  useEffect(() => {
    if (!peData || !peChart.current) return;

    const dates = peData.peLine.map((item) => item.date);
    const buildHorizontalLine = (value: number) => dates.map((date) => [date, value]);

    peChart.current.clear();
    peChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: { trigger: "axis" },
        legend: { top: 8, data: ["公司市盈率", "均值线", "低估线", "高估线"] },
        grid: { top: 56, left: 64, right: 64, bottom: 44, containLabel: true },
        xAxis: {
          type: "time",
          boundaryGap: false,
          axisLabel: {
            hideOverlap: true,
            formatter(value: number) {
              return echarts.time.format(value, "{yyyy}-{MM}-{dd}", false);
            },
          },
        },
        yAxis: {
          type: "value",
          name: `市盈率(${peData.unit})`,
          splitLine: { lineStyle: { color: "#e8edf5" } },
        },
        series: [
          {
            name: "公司市盈率",
            type: "line",
            showSymbol: false,
            smooth: true,
            data: peData.peLine.map((item) => [item.date, item.value]),
            lineStyle: { width: 2, color: "#4e79ff" },
            itemStyle: { color: "#4e79ff" },
          },
          {
            name: "均值线",
            type: "line",
            showSymbol: false,
            data: buildHorizontalLine(peData.meanLine),
            lineStyle: { type: "dashed", width: 2, color: "#f2d74e" },
            itemStyle: { color: "#f2d74e" },
          },
          {
            name: "低估线",
            type: "line",
            showSymbol: false,
            data: buildHorizontalLine(peData.lowLine),
            lineStyle: { type: "dashed", width: 2, color: "#3f8f63" },
            itemStyle: { color: "#3f8f63" },
          },
          {
            name: "高估线",
            type: "line",
            showSymbol: false,
            data: buildHorizontalLine(peData.highLine),
            lineStyle: { type: "dashed", width: 2, color: "#d93025" },
            itemStyle: { color: "#d93025" },
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => peChart.current?.resize());
  }, [peData, selectedCharts]);

  useEffect(() => {
    if (!profitData || !profitChart.current) return;

    const allDates = [...profitData.profitBars, ...profitData.marketCapLine]
      .map((item) => new Date(item.date).getTime())
      .filter((value) => Number.isFinite(value))
      .sort((left, right) => left - right);

    const xMin = allDates[0];
    const xMax = allDates[allDates.length - 1];

    profitChart.current.clear();
    profitChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: { trigger: "axis" },
        legend: { top: 8, data: ["归母净利润", "总市值"] },
        grid: { top: 56, left: 64, right: 56, bottom: 44, containLabel: true },
        xAxis: {
          type: "time",
          min: Number.isFinite(xMin) ? xMin : undefined,
          max: Number.isFinite(xMax) ? xMax : undefined,
          boundaryGap: false,
          axisLabel: {
            hideOverlap: true,
            formatter(value: number) {
              return echarts.time.format(value, "{yyyy}", false);
            },
          },
        },
        yAxis: [
          {
            type: "value",
            name: profitData.leftAxisName,
            axisLabel: { color: "#3f5fe8" },
            nameTextStyle: { color: "#3f5fe8" },
            splitLine: { lineStyle: { color: "#e8edf5" } },
          },
          {
            type: "value",
            name: profitData.rightAxisName,
            axisLabel: { color: "#e05555" },
            nameTextStyle: { color: "#e05555" },
            axisLine: { show: true, lineStyle: { color: "#e05555" } },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: "归母净利润",
            type: "bar",
            yAxisIndex: 0,
            barMaxWidth: 22,
            label: { show: false },
            itemStyle: { color: "#4e79ff" },
            markLine: {
              symbol: "none",
              silent: true,
              label: { formatter: "净利润 0 线", color: "#64748b" },
              lineStyle: { color: "#94a3b8", type: "dashed", width: 1 },
              data: [{ yAxis: 0 }],
            },
            data: profitData.profitBars.map((item) => [item.date, item.value]),
          },
          {
            name: "总市值",
            type: "line",
            yAxisIndex: 1,
            showSymbol: false,
            smooth: true,
            label: { show: false },
            itemStyle: { color: "#e05555" },
            lineStyle: { color: "#e05555", width: 2 },
            data: profitData.marketCapLine.map((item) => [item.date, item.value]),
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => profitChart.current?.resize());
  }, [profitData, selectedCharts]);

  useEffect(() => {
    if (!cashFlowData || !cashFlowChart.current) return;

    const allDates = [
      ...cashFlowData.operatingCashFlow,
      ...cashFlowData.netProfit,
      ...cashFlowData.cashToProfitRatio,
    ]
      .map((item) => new Date(item.date).getTime())
      .filter((value) => Number.isFinite(value))
      .sort((left, right) => left - right);

    const xMin = allDates[0];
    const xMax = allDates[allDates.length - 1];

    cashFlowChart.current.clear();
    cashFlowChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: {
          trigger: "axis",
          valueFormatter: (value: number | string) => {
            if (typeof value !== "number") return `${value}`;
            return Number.isFinite(value) ? value.toFixed(2) : "-";
          },
        },
        legend: { top: 8, data: ["经营现金流", "归母净利润", "净现比"] },
        grid: { top: 56, left: 64, right: 56, bottom: 44, containLabel: true },
        xAxis: {
          type: "time",
          min: Number.isFinite(xMin) ? xMin : undefined,
          max: Number.isFinite(xMax) ? xMax : undefined,
          boundaryGap: false,
          axisLabel: {
            hideOverlap: true,
            formatter(value: number) {
              return echarts.time.format(value, "{yyyy}", false);
            },
          },
        },
        yAxis: [
          { type: "value", name: "金额(亿元)", splitLine: { lineStyle: { color: "#e8edf5" } } },
          { type: "value", name: "净现比", splitLine: { show: false } },
        ],
        series: [
          {
            name: "经营现金流",
            type: "bar",
            yAxisIndex: 0,
            barMaxWidth: 18,
            itemStyle: { color: "#087f5b" },
            data: cashFlowData.operatingCashFlow.map((item) => [item.date, item.value]),
          },
          {
            name: "归母净利润",
            type: "bar",
            yAxisIndex: 0,
            barMaxWidth: 18,
            itemStyle: { color: "#4e79ff" },
            data: cashFlowData.netProfit.map((item) => [item.date, item.value]),
          },
          {
            name: "净现比",
            type: "line",
            yAxisIndex: 1,
            showSymbol: false,
            smooth: true,
            lineStyle: { color: "#b7791f", width: 2 },
            itemStyle: { color: "#b7791f" },
            data: cashFlowData.cashToProfitRatio.map((item) => [item.date, item.value]),
          },
        ],
      },
      { notMerge: true }
    );

    requestAnimationFrame(() => cashFlowChart.current?.resize());
  }, [cashFlowData, selectedCharts]);

  async function loadBalanceData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setBalanceStatus("正在加载 AKShare 资产负债数据...");
    setBalanceError(null);

    try {
      const params = new URLSearchParams({ stock: query.stock });
      if (query.period) params.set("period", query.period);

      const response = await fetch(`${API_BASE}/api/balance?${params.toString()}`);
      const data = (await response.json()) as BalanceResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "资产负债接口请求失败");

      setBalanceData(data);
      setBalanceStatus("加载完成");
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "加载失败";
      setBalanceError(message);
      setBalanceStatus(`加载失败：${message}`);
    }
  }

  async function loadTrendData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setTrendStatus("正在加载 AKShare 业绩与市值数据...");
    setTrendError(null);

    try {
      const params = new URLSearchParams({ stock: query.stock, years: query.years });
      const response = await fetch(`${API_BASE}/api/revenue-market-cap?${params.toString()}`);
      const data = (await response.json()) as TrendResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "业绩与市值接口请求失败");

      setTrendData(data);
      setTrendStatus("加载完成");
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "加载失败";
      setTrendError(message);
      setTrendStatus(`加载失败：${message}`);
    }
  }

  async function loadPeData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setPeStatus("正在加载 AKShare 市盈率数据...");
    setPeError(null);

    try {
      const params = new URLSearchParams({ stock: query.stock, years: query.years });
      const response = await fetch(`${API_BASE}/api/pe-trend?${params.toString()}`);
      const data = (await response.json()) as PeTrendResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "市盈率接口请求失败");

      setPeData(data);
      setPeStatus("加载完成");
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "加载失败";
      setPeError(message);
      setPeStatus(`加载失败：${message}`);
    }
  }

  async function loadProfitMarketCapData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setProfitStatus("正在加载 AKShare 净利润与市值数据...");
    setProfitError(null);

    try {
      const params = new URLSearchParams({ stock: query.stock, years: query.years });
      const response = await fetch(`${API_BASE}/api/profit-market-cap?${params.toString()}`);
      const data = (await response.json()) as ProfitMarketCapResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "净利润与市值接口请求失败");

      setProfitData(data);
      setProfitStatus("加载完成");
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "加载失败";
      setProfitError(message);
      setProfitStatus(`加载失败：${message}`);
    }
  }

  async function loadCashFlowQualityData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setCashFlowStatus("正在加载 AKShare 现金流质量数据...");
    setCashFlowError(null);

    try {
      const params = new URLSearchParams({ stock: query.stock, years: query.years });
      const response = await fetch(`${API_BASE}/api/cash-flow-quality?${params.toString()}`);
      const data = (await response.json()) as CashFlowQualityResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "现金流质量接口请求失败");

      setCashFlowData(data);
      setCashFlowStatus("加载完成");
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "加载失败";
      setCashFlowError(message);
      setCashFlowStatus(`加载失败：${message}`);
    }
  }

  async function loadRevenueStructureData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setRevenueStructureStatus("正在加载公司收入结构拆解...");
    setRevenueStructureError(null);
    setRevenueStructureData(null);

    try {
      const params = new URLSearchParams({ stock: query.stock, years: query.years });
      const response = await fetch(`${API_BASE}/api/revenue-structure?${params.toString()}`);
      const data = (await response.json()) as RevenueStructureResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "收入结构接口请求失败");

      setRevenueStructureData(data);
      setRevenueStructureStatus("加载完成");
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "加载失败";
      setRevenueStructureError(message);
      setRevenueStructureStatus(`加载失败：${message}`);
    }
  }

  async function loadPeerCompaniesData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setPeerStatus("正在识别同行竞品...");
    setPeerError(null);

    try {
      const params = new URLSearchParams({ stock: query.stock, limit: "6" });
      const response = await fetch(`${API_BASE}/api/peer-companies?${params.toString()}`);
      const data = (await response.json()) as PeerCompaniesResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "同行竞品接口请求失败");

      setPeerData(data);
      setPeerStatus(data.sourceLabel ? `同行竞品：${data.sourceLabel}` : "同行竞品已加载");
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "加载失败";
      setPeerData(null);
      setPeerError(message);
      setPeerStatus(`同行竞品加载失败：${message}`);
    }
  }

  async function loadSystemStatus() {
    setHealthError(null);

    try {
      const [healthResponse, cacheResponse] = await Promise.all([
        fetch(`${API_BASE}/api/health`),
        fetch(`${API_BASE}/api/cache/stats?limit=5`),
      ]);

      const healthPayload = (await healthResponse.json()) as HealthResponse & { error?: string };
      const cachePayload = (await cacheResponse.json()) as CacheStatsResponse & { error?: string };

      if (!healthResponse.ok) throw new Error(healthPayload.error || "健康检查请求失败");
      if (!cacheResponse.ok) throw new Error(cachePayload.error || "缓存统计请求失败");

      setHealthData(healthPayload);
      setCacheStats(cachePayload);
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "系统状态加载失败";
      setHealthError(message);
    }
  }

  async function loadAllData(overrides?: Partial<QueryState>) {
    const query = getQueryState(overrides);
    setAiData(null);
    setAiError(null);
    setAiStatus("点击“生成 AI 分析”获取综合解读");
    setRevenueStructureData(null);
    syncUrl(query);

    await Promise.all([
      loadBalanceData(query),
      loadTrendData(query),
      loadPeData(query),
      loadProfitMarketCapData(query),
      loadCashFlowQualityData(query),
      loadRevenueStructureData(query),
      loadPeerCompaniesData(query),
      loadSystemStatus(),
    ]);
  }

  async function loadAiAnalysis() {
    setAiStatus("正在生成 OpenAI 财报分析...");
    setAiError(null);

    try {
      const response = await fetch(`${API_BASE}/api/ai-analysis`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          stock: getQueryState().stock,
          period: getQueryState().period || null,
          years: Number(getQueryState().years),
        }),
      });

      const data = (await response.json()) as AiAnalysisResponse & { error?: string };
      if (!response.ok) throw new Error(data.error || "AI 分析接口请求失败");

      setAiData(data);
      setAiStatus(`AI 分析已生成，模型：${data.model}`);
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "AI 分析生成失败";
      setAiError(message);
      setAiStatus(`AI 分析失败：${message}`);
    }
  }

  function applyStockPreset(nextStock: string) {
    setStock(nextStock);
    void loadAllData({ stock: nextStock });
  }

  function toggleChart(chartId: ChartId) {
    setSelectedCharts((current) => {
      if (current.includes(chartId)) {
        return current.length > 1 ? current.filter((item) => item !== chartId) : current;
      }

      return [...current, chartId];
    });
  }

  const combinedStatus = formatCombinedStatus([
    balanceStatus,
    trendStatus,
    peStatus,
    profitStatus,
    cashFlowStatus,
    revenueStructureStatus,
    peerStatus,
  ]);
  const combinedError = [balanceError, trendError, peError, profitError, cashFlowError, revenueStructureError, peerError]
    .filter(Boolean)
    .join(" | ");
  const peerPresets =
    peerData?.peers?.map((peer) => ({
      code: peer.stock,
      label: peer.name,
    })) ?? [];
  const chartGridClass = `chart-grid custom-chart-grid count-${Math.min(selectedCharts.length, 5)}`;

  return (
    <main className="page-shell">
      <QueryBar
        stock={stock}
        period={period}
        years={years}
        presets={peerPresets}
        combinedStatus={combinedStatus}
        combinedError={combinedError}
        onStockChange={setStock}
        onPeriodChange={setPeriod}
        onYearsChange={setYears}
        onQuery={() => void loadAllData()}
        onPresetSelect={applyStockPreset}
      />

      <section className="chart-picker" aria-label="图表选择器">
        <div className="chart-toggle-group">
          {CHART_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`chart-toggle ${selectedCharts.includes(option.id) ? "active" : ""}`}
              onClick={() => toggleChart(option.id)}
              aria-pressed={selectedCharts.includes(option.id)}
            >
              <span>{option.label}</span>
              <small>{option.description}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="chart-workspace" aria-label="已选图表">
        <div className={chartGridClass}>
          {selectedCharts.includes("revenue") ? (
            <ChartPanel key="revenue-chart" title={trendData?.title ?? "公司市值与业绩增长趋势"} chartRef={trendChartRef} />
          ) : null}

          {selectedCharts.includes("profit") ? (
            <ChartPanel key="profit-chart" title={profitData?.title ?? "净利润与市值对比"} chartRef={profitChartRef}>
              {profitData?.conclusion ? <div className="status">{profitData.conclusion}</div> : null}
            </ChartPanel>
          ) : null}

          {selectedCharts.includes("cashflow") ? (
            <ChartPanel key="cashflow-chart" title={cashFlowData?.title ?? "现金流与盈利质量"} chartRef={cashFlowChartRef}>
              {cashFlowData?.conclusion ? <div className="status">{cashFlowData.conclusion}</div> : null}
            </ChartPanel>
          ) : null}

          {selectedCharts.includes("balance") ? (
            <ChartPanel key="balance-chart" title={balanceData?.title ?? "资产负债结构图"} chartRef={balanceChartRef} />
          ) : null}

          {selectedCharts.includes("pe") ? (
            <ChartPanel key="pe-chart" title={peData?.title ?? "市盈率趋势图"} chartRef={peChartRef}>
              <div className="status">
                均值线：{peData?.meanLine ?? "-"}，低估线：{peData?.lowLine ?? "-"}，高估线：
                {peData?.highLine ?? "-"}
              </div>
              {peData?.conclusion ? <div className="status">{peData.conclusion}</div> : null}
            </ChartPanel>
          ) : null}
        </div>
      </section>

      <section aria-label="业务结构">
        <BusinessModelSection
        title="公司靠什么赚钱"
        description={
          <>
            把收入按{primaryUnitLabel}、地区、渠道拆开看，先判断谁贡献收入、谁最赚钱、有没有单一业务依赖。
          </>
        }
        meta={
          <>
            {revenueStructureData?.companyName || stock}
            {revenueStructureData?.reportDate ? ` · ${revenueStructureData.reportDate}` : ""}
          </>
        }
      >
        {revenueStructureError ? <div className="error-box">{revenueStructureError}</div> : null}

        {revenueStructureData ? (
          <>
          <AutoConclusionStrip items={autoConclusionItems} />

          <div className="overview-grid">
            <div className="revenue-section-card overview-card">
              <h4>综合判断</h4>
              <div className="overview-headline">
                {autoConclusionItems.map((item) => `${item.label}：${item.value}`).join(" · ")}
              </div>
              <div className="subtle">
                {cashFlowData?.conclusion ||
                  profitData?.conclusion ||
                  "等待财务数据加载完成后生成判断。"}
              </div>
            </div>

            <div className="revenue-section-card overview-card">
              <h4>关键证据</h4>
              <div className="overview-list">
                {buildPerformanceInsightPoints(profitData, trendData)
                  .slice(0, 3)
                  .map((item) => (
                    <div key={item} className="overview-evidence">
                      {item}
                    </div>
                  ))}
                {cashFlowData?.conclusion ? <div className="overview-evidence">{cashFlowData.conclusion}</div> : null}
              </div>
            </div>
          </div>

          <div className="revenue-structure-grid">
            <div className="revenue-summary-card">
              <div className="summary-kicker">核心业务</div>
              <div className="summary-headline">
                {revenueStructureData.highlights.topProduct?.itemName || "未识别核心产品"}
              </div>
              <div className="summary-copy">
                收入占比 {formatPercent(revenueStructureData.highlights.topProduct?.revenueRatio)}，自身毛利率{" "}
                {formatPercent(revenueStructureData.breakdowns.byProduct[0]?.grossMargin)}
              </div>
              <div className="summary-copy">
                {revenueStructureData.businessSummary.interpretedMainBusiness ||
                  revenueStructureData.businessSummary.mainBusiness ||
                  "暂无主营业务摘要"}
              </div>
              <div className="summary-copy">
                类型判断：{companyNatureLabel}
                {displayedPositioning?.confidence !== undefined
                  ? ` · 置信度 ${formatConfidence(displayedPositioning.confidence)}`
                  : ""}
              </div>
              {displayedPositioning?.rationale ? (
                <div className="summary-copy">
                  为什么按{primaryUnitLabel}看：{displayedPositioning.rationale}
                </div>
              ) : null}
              {watchMetrics.length ? (
                <div className="summary-copy">重点跟踪：{watchMetrics.join("、")}</div>
              ) : null}
            </div>

            <div className="revenue-metric-grid">
              <div className="mini-metric-card">
                <div className="mini-metric-label">公司类型</div>
                <div className="mini-metric-value">{companyNatureLabel}</div>
                <div className="mini-metric-sub">置信度 {formatConfidence(displayedPositioning?.confidence)}</div>
              </div>

              <div className="mini-metric-card">
                <div className="mini-metric-label">第一大{primaryUnitLabel}</div>
                <div className="mini-metric-value">{revenueStructureData.highlights.topProduct?.itemName || "-"}</div>
                <div className="mini-metric-sub">
                  {formatPercent(revenueStructureData.highlights.topProduct?.revenueRatio)}
                </div>
              </div>

              <div className="mini-metric-card">
                <div className="mini-metric-label">毛利最高{primaryUnitLabel}</div>
                <div className="mini-metric-value">
                  {revenueStructureData.highlights.bestGrossMarginProduct?.itemName || "-"}
                </div>
                <div className="mini-metric-sub">
                  {formatPercent(revenueStructureData.highlights.bestGrossMarginProduct?.grossMargin)}
                </div>
              </div>

              <div className="mini-metric-card">
                <div className="mini-metric-label">第一大区域</div>
                <div className="mini-metric-value">{revenueStructureData.highlights.topRegion?.itemName || "-"}</div>
                <div className="mini-metric-sub">
                  {formatPercent(revenueStructureData.highlights.topRegion?.revenueRatio)}
                </div>
              </div>
            </div>

            <div className="revenue-section-card revenue-section-card-wide">
              <h4>证据链</h4>
              <div className="positioning-grid">
                <div className="positioning-column">
                  <div className="positioning-title">支持证据</div>
                  {supportEvidence.length ? (
                    supportEvidence.map((item) => (
                      <div key={`${item.type}-${item.label}`} className="positioning-item">
                        <div className="positioning-item-label">{item.label}</div>
                        <div className="positioning-item-detail">{item.detail}</div>
                      </div>
                    ))
                  ) : (
                    <div className="subtle">
                      {aiPositioning
                        ? "这次 AI 也没有给出足够强的支持证据，说明当前判断仍偏弱。"
                        : "当前还是规则兜底阶段，建议点击“生成 AI 分析”后再看支持证据。"}
                    </div>
                  )}
                </div>

                <div className="positioning-column">
                  <div className="positioning-title">冲突证据</div>
                  {conflictEvidence.length ? (
                    conflictEvidence.map((item) => (
                      <div key={`${item.type}-${item.label}`} className="positioning-item positioning-item-warning">
                        <div className="positioning-item-label">{item.label}</div>
                        <div className="positioning-item-detail">{item.detail}</div>
                      </div>
                    ))
                  ) : (
                    <div className="subtle">
                      {aiPositioning
                        ? "当前没有明显反向证据，AI 认为主导模式相对单一。"
                        : "当前没有抓到明确反向信号，但这并不代表判断已经足够强。"}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="revenue-section-card">
              <h4>按{primaryUnitLabel}</h4>
              {renderBreakdownRows(revenueStructureData.breakdowns.byProduct)}
            </div>

            <div className="revenue-section-card">
              <h4>按地区</h4>
              {renderBreakdownRows(revenueStructureData.breakdowns.byRegion)}
            </div>

            <div className="revenue-section-card revenue-section-card-wide">
              <h4>按渠道</h4>
              {revenueStructureData.breakdowns.byChannel.length ? (
                renderBreakdownRows(revenueStructureData.breakdowns.byChannel)
              ) : (
                <div className="subtle">当前报告里没有抽取到稳定的渠道拆分数据。</div>
              )}
            </div>
          </div>
          </>
        ) : null}
        </BusinessModelSection>
      </section>

      <section aria-label="AI 分析和系统状态">
        <AiAnalysisSection
        status={aiStatus}
        error={aiError}
        action={
          <button className="query-button" onClick={() => void loadAiAnalysis()}>
            生成 AI 分析
          </button>
        }
      >
        {aiData?.businessTypeAnalysis ? (
          <div className="business-type-summary">
            <div className="business-type-chip">商业模式：{aiData.businessTypeAnalysis.business_type}</div>
            <div className="subtle">
              置信度：{aiData.businessTypeAnalysis.confidence} | 核心收入：
              {aiData.businessTypeAnalysis.main_revenue_source || "未明确"}
            </div>
          </div>
        ) : null}
        {aiData?.analysis ? <div className="ai-content">{aiData.analysis}</div> : null}
      </AiAnalysisSection>

      <SystemStatus
        error={healthError}
        action={
          <button type="button" className="query-button secondary-button" onClick={() => void loadSystemStatus()}>
            刷新状态
          </button>
        }
      >
        <div className="system-grid">
          <div className="mini-metric-card">
            <div className="mini-metric-label">后端服务</div>
            <div className="mini-metric-value">{healthData?.status === "ok" ? "正常" : "-"}</div>
            <div className="mini-metric-sub">{healthData?.service || "未连接"}</div>
          </div>

          <div className="mini-metric-card">
            <div className="mini-metric-label">运行时长</div>
            <div className="mini-metric-value">{formatUptime(healthData?.uptimeSeconds)}</div>
            <div className="mini-metric-sub">Python {healthData?.pythonVersion || "-"}</div>
          </div>

          <div className="mini-metric-card">
            <div className="mini-metric-label">缓存文件数</div>
            <div className="mini-metric-value">{cacheStats?.cache.fileCount ?? "-"}</div>
            <div className="mini-metric-sub">{cacheStats?.cache.exists ? "缓存目录可用" : "缓存目录不可用"}</div>
          </div>

          <div className="mini-metric-card">
            <div className="mini-metric-label">缓存体积</div>
            <div className="mini-metric-value">{formatBytes(cacheStats?.cache.totalBytes)}</div>
            <div className="mini-metric-sub">{cacheStats?.cache.directory || "-"}</div>
          </div>
        </div>

        <div className="revenue-section-card system-files-card">
          <h4>最近缓存文件</h4>
          {cacheStats?.recentFiles.length ? (
            cacheStats.recentFiles.map((item) => (
              <div key={item.name} className="revenue-row">
                <div>
                  <div className="revenue-row-title">{item.name}</div>
                  <div className="revenue-row-meta">{item.modifiedAt}</div>
                </div>
                <div className="revenue-row-side">
                  <div>{formatBytes(item.sizeBytes)}</div>
                </div>
              </div>
            ))
          ) : (
            <div className="subtle">当前还没有读取到缓存文件列表。</div>
          )}
        </div>
        </SystemStatus>
      </section>
    </main>
  );
}
