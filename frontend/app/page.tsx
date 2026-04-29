"use client";

import {
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
  type RefObject,
} from "react";
import * as echarts from "echarts";

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
  confidence: number;
  main_revenue_source: string;
  main_profit_source: string;
  growth_driver: string;
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:5001";

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

export default function HomePage() {
  const [stock, setStock] = useState("600519");
  const [period, setPeriod] = useState("");
  const [years, setYears] = useState("8");

  const [balanceStatus, setBalanceStatus] = useState("正在加载资产负债数据...");
  const [trendStatus, setTrendStatus] = useState("正在加载业绩与市值数据...");
  const [peStatus, setPeStatus] = useState("正在加载市盈率数据...");
  const [profitStatus, setProfitStatus] = useState("正在加载净利润与市值数据...");

  const [aiStatus, setAiStatus] = useState("点击“生成 AI 分析”获取综合解读");

  const [balanceError, setBalanceError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [peError, setPeError] = useState<string | null>(null);
  const [profitError, setProfitError] = useState<string | null>(null);

  const [aiError, setAiError] = useState<string | null>(null);

  const [balanceData, setBalanceData] = useState<BalanceResponse | null>(null);
  const [trendData, setTrendData] = useState<TrendResponse | null>(null);
  const [peData, setPeData] = useState<PeTrendResponse | null>(null);
  const [profitData, setProfitData] = useState<ProfitMarketCapResponse | null>(null);

  const [aiData, setAiData] = useState<AiAnalysisResponse | null>(null);

  const balanceChartRef = useRef<HTMLDivElement | null>(null);
  const trendChartRef = useRef<HTMLDivElement | null>(null);
  const peChartRef = useRef<HTMLDivElement | null>(null);
  const profitChartRef = useRef<HTMLDivElement | null>(null);

  const balanceChart = useRef<echarts.ECharts | null>(null);
  const trendChart = useRef<echarts.ECharts | null>(null);
  const peChart = useRef<echarts.ECharts | null>(null);
  const profitChart = useRef<echarts.ECharts | null>(null);

  function ensureChart(
    ref: RefObject<HTMLDivElement | null>,
    instanceRef: MutableRefObject<echarts.ECharts | null>
  ) {
    if (!ref.current) return;
    instanceRef.current = echarts.getInstanceByDom(ref.current) ?? echarts.init(ref.current);
  }

  useEffect(() => {
    ensureChart(balanceChartRef, balanceChart);
    ensureChart(trendChartRef, trendChart);
    ensureChart(peChartRef, peChart);
    ensureChart(profitChartRef, profitChart);

    const handleResize = () => {
      balanceChart.current?.resize();
      trendChart.current?.resize();
      peChart.current?.resize();
      profitChart.current?.resize();
    };

    window.addEventListener("resize", handleResize);
    requestAnimationFrame(handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      balanceChart.current?.dispose();
      trendChart.current?.dispose();
      peChart.current?.dispose();
      profitChart.current?.dispose();
    };
  }, []);

  useEffect(() => {
    void loadAllData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
  }, [balanceData]);

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
          { type: "value", name: trendData.leftAxisName, splitLine: { lineStyle: { color: "#e8edf5" } } },
          { type: "value", name: trendData.rightAxisName, splitLine: { show: false } },
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
  }, [trendData]);

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
  }, [peData]);

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
          { type: "value", name: profitData.leftAxisName, splitLine: { lineStyle: { color: "#e8edf5" } } },
          { type: "value", name: profitData.rightAxisName, splitLine: { show: false } },
        ],
        series: [
          {
            name: "归母净利润",
            type: "bar",
            yAxisIndex: 0,
            barMaxWidth: 22,
            label: { show: false },
            itemStyle: { color: "#4e79ff" },
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
  }, [profitData]);

  async function loadBalanceData() {
    setBalanceStatus("正在加载 AKShare 资产负债数据...");
    setBalanceError(null);

    try {
      const params = new URLSearchParams({ stock: stock || "600519" });
      if (period.trim()) params.set("period", period.trim());

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

  async function loadTrendData() {
    setTrendStatus("正在加载 AKShare 业绩与市值数据...");
    setTrendError(null);

    try {
      const params = new URLSearchParams({ stock: stock || "600519", years: years || "8" });
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

  async function loadPeData() {
    setPeStatus("正在加载 AKShare 市盈率数据...");
    setPeError(null);

    try {
      const params = new URLSearchParams({ stock: stock || "600519", years: years || "8" });
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

  async function loadProfitMarketCapData() {
    setProfitStatus("正在加载 AKShare 净利润与市值数据...");
    setProfitError(null);

    try {
      const params = new URLSearchParams({ stock: stock || "600519", years: years || "8" });
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

  async function loadAllData() {
    setAiData(null);
    setAiError(null);
    setAiStatus("点击“生成 AI 分析”获取综合解读");

    await Promise.all([
      loadBalanceData(),
      loadTrendData(),
      loadPeData(),
      loadProfitMarketCapData(),
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
          stock: stock || "600519",
          period: period.trim() || null,
          years: Number(years || "8"),
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

  const combinedStatus = [balanceStatus, trendStatus, peStatus, profitStatus].join(" | ");
  const combinedError = [balanceError, trendError, peError, profitError]
    .filter(Boolean)
    .join(" | ");

  return (
    <main className="page-shell">
      <section className="panel">
        <div className="topbar">
          <div>
            <h1>财报可视化分析系统</h1>
            <div className="meta-row">
              <span>资产负债：{balanceData?.reportDate ?? "-"}</span>
              <span>趋势范围：最近 {years} 年</span>
            </div>
          </div>

          <div className="controls unified-controls">
            <label className="field">
              股票
              <input value={stock} onChange={(e) => setStock(e.target.value)} />
            </label>

            <label className="field">
              报告期
              <input
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                placeholder="20241231，可不填"
              />
            </label>

            <label className="field">
              最近几年
              <input value={years} onChange={(e) => setYears(e.target.value)} />
            </label>

            <button className="query-button" onClick={() => void loadAllData()}>
              查询
            </button>
          </div>
        </div>

        <div className="status">{combinedStatus}</div>
        {combinedError ? <div className="error-box">{combinedError}</div> : null}
      </section>

      <section className="panel">
        <div className="chart-card ai-card">
          <div className="ai-card-header">
            <div>
              <h3>OpenAI 财报综合分析</h3>
              <div className="subtle">结合资产负债、营收、市值、净利润和市盈率做整体解读，并自动判断商业模式类型。</div>
            </div>

            <button className="query-button" onClick={() => void loadAiAnalysis()}>
              生成 AI 分析
            </button>
          </div>

          <div className="status">{aiStatus}</div>
          {aiError ? <div className="error-box">{aiError}</div> : null}
          {aiData?.businessTypeAnalysis ? (
            <div className="business-type-summary">
              <div className="business-type-chip">
                商业模式：{aiData.businessTypeAnalysis.business_type}
              </div>
              <div className="subtle">
                置信度：{aiData.businessTypeAnalysis.confidence} | 核心收入：
                {aiData.businessTypeAnalysis.main_revenue_source || "未明确"}
              </div>
            </div>
          ) : null}
          {aiData?.analysis ? <div className="ai-content">{aiData.analysis}</div> : null}
        </div>
      </section>

      <section className="panel">
        <div className="chart-columns">
          <article className="chart-block">
            <div className="chart-card">
              <h3>{balanceData?.title ?? "600519 资产负债结构图"}</h3>
              <div ref={balanceChartRef} className="chart-box compact-chart" />
            </div>
          </article>

          <article className="chart-block">
            <div className="chart-card">
              <h3>{trendData?.title ?? "600519 公司市值与业绩增长趋势"}</h3>
              <div ref={trendChartRef} className="chart-box compact-chart" />
            </div>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="chart-columns">
          <article className="chart-block">
            <div className="chart-card">
              <h3>{peData?.title ?? "市盈率趋势图"}</h3>
              <div ref={peChartRef} className="chart-box compact-chart" />

              <div className="status">
                均值线：{peData?.meanLine ?? "-"}， 低估线：
                {peData?.lowLine ?? "-"}， 高估线：{peData?.highLine ?? "-"}
              </div>

              {peData?.conclusion ? <div className="status">{peData.conclusion}</div> : null}
            </div>
          </article>

          <article className="chart-block">
            <div className="chart-card">
              <h3>{profitData?.title ?? "净利润与市值对比"}</h3>
              <div ref={profitChartRef} className="chart-box compact-chart" />

              {profitData?.conclusion ? (
                <div className="status">{profitData.conclusion}</div>
              ) : null}
            </div>
          </article>
        </div>
      </section>
    </main>
  );
}
