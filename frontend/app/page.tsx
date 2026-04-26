"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:5001";

export default function HomePage() {
  const [stock, setStock] = useState("600519");
  const [period, setPeriod] = useState("");
  const [years, setYears] = useState("8");

  const [balanceStatus, setBalanceStatus] = useState("正在加载资产负债数据...");
  const [trendStatus, setTrendStatus] = useState("正在加载业绩与市值数据...");
  const [balanceError, setBalanceError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [balanceData, setBalanceData] = useState<BalanceResponse | null>(null);
  const [trendData, setTrendData] = useState<TrendResponse | null>(null);

  const balanceChartRef = useRef<HTMLDivElement | null>(null);
  const trendChartRef = useRef<HTMLDivElement | null>(null);
  const balanceChart = useRef<echarts.ECharts | null>(null);
  const trendChart = useRef<echarts.ECharts | null>(null);

  const prettyJson = useMemo(
    () =>
      JSON.stringify(
        {
          balanceData,
          trendData,
        },
        null,
        2
      ),
    [balanceData, trendData]
  );

  function ensureChart(
    ref: React.RefObject<HTMLDivElement | null>,
    instanceRef: React.MutableRefObject<echarts.ECharts | null>
  ) {
    if (!ref.current) {
      return;
    }
    instanceRef.current = echarts.getInstanceByDom(ref.current) ?? echarts.init(ref.current);
  }

  useEffect(() => {
    ensureChart(balanceChartRef, balanceChart);
    ensureChart(trendChartRef, trendChart);

    const handleResize = () => {
      balanceChart.current?.resize();
      trendChart.current?.resize();
    };

    window.addEventListener("resize", handleResize);
    requestAnimationFrame(handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      balanceChart.current?.dispose();
      trendChart.current?.dispose();
    };
  }, []);

  useEffect(() => {
    void loadAllData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!balanceData || !balanceChart.current) {
      return;
    }

    const colors = balanceData.barData.map((item) =>
      item.type === "asset" ? "#4e79ff" : "#e05555"
    );

    balanceChart.current.clear();
    balanceChart.current.setOption(
      {
        animationDuration: 400,
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
        },
        grid: { top: 24, left: 8, right: 16, bottom: 16, containLabel: true },
        xAxis: {
          type: "value",
          name: balanceData.unit,
          splitLine: { lineStyle: { color: "#e8edf5" } },
        },
        yAxis: {
          type: "category",
          data: balanceData.barData.map((item) => item.name),
          axisLabel: {
            margin: 4,
          },
        },
        series: [
          {
            type: "bar",
            label: { show: true, position: "right", formatter: "{c}" },
            data: balanceData.barData.map((item, index) => ({
              value: item.value,
              itemStyle: { color: colors[index] },
            })),
          },
        ],
      },
      { notMerge: true }
    );
    requestAnimationFrame(() => balanceChart.current?.resize());
  }, [balanceData]);

  useEffect(() => {
    if (!trendData || !trendChart.current) {
      return;
    }

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
        legend: {
          top: 8,
          data: ["营业总收入", "总市值"],
        },
        grid: {
          top: 56,
          left: 64,
          right: 28,
          bottom: 44,
          containLabel: true,
        },
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
            splitLine: { lineStyle: { color: "#e8edf5" } },
          },
          {
            type: "value",
            name: trendData.rightAxisName,
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
  }, [trendData]);

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
      const params = new URLSearchParams({
        stock: stock || "600519",
        years: years || "8",
      });
      const response = await fetch(
        `${API_BASE}/api/revenue-market-cap?${params.toString()}`
      );
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

  async function loadAllData() {
    await Promise.all([loadBalanceData(), loadTrendData()]);
  }

  const combinedStatus = [balanceStatus, trendStatus].join(" | ");
  const combinedError = [balanceError, trendError].filter(Boolean).join(" | ");

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
        <div className="chart-columns">
          <article className="chart-block">
            <div className="chart-card">
              <h3>{balanceData?.title ?? "600519 资产负债结构图"}</h3>
              <div ref={balanceChartRef} className="chart-box compact-chart" />
            </div>
          </article>

          <article className="chart-block">
            <div className="chart-card">
              <h3>{trendData?.title ?? "000333 公司市值与业绩增长趋势"}</h3>
              <div ref={trendChartRef} className="chart-box compact-chart" />
            </div>
          </article>
        </div>
      </section>

      <section className="panel">
        <h2>接口返回预览</h2>
        <pre className="json-box">{prettyJson}</pre>
      </section>
    </main>
  );
}
