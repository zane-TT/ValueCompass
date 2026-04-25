"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type YearlyFinancialData = {
  year: string;
  revenue: number | null;
  net_profit: number | null;
  total_assets: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
};

type FinancialHistoryResponse = {
  ticker: string;
  company_name: string;
  yearly_data: YearlyFinancialData[];
  fetched_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function FinancialHistoryPage() {
  const [ticker, setTicker] = useState("600519");
  const [startYear, setStartYear] = useState("2010");
  const [endYear, setEndYear] = useState("2025");
  const [data, setData] = useState<FinancialHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/financial-history`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          start_year: startYear,
          end_year: endYear,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Failed to fetch data");
      }

      const result = (await res.json()) as FinancialHistoryResponse;
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
  }, []);

  const getRevenueChartOption = () => {
    if (!data) return {};

    const sortedData = [...data.yearly_data].sort(
      (a, b) => parseInt(a.year) - parseInt(b.year)
    );

    return {
      title: {
        text: `${data.company_name} (${data.ticker}) 营业收入历年变化`,
        left: "center",
      },
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => {
          const item = params[0];
          const value = item.value;
          return `${item.name}<br/>营收: ¥${(value / 100000000).toFixed(2)}亿`;
        },
      },
      xAxis: {
        type: "category",
        data: sortedData.map((d) => d.year),
        name: "年份",
      },
      yAxis: {
        type: "value",
        name: "营收 (亿元)",
        axisLabel: {
          formatter: (value: number) => (value / 100000000).toFixed(0),
        },
      },
      series: [
        {
          name: "营业收入",
          type: "bar",
          data: sortedData.map((d) => d.revenue ?? 0),
          itemStyle: { color: "#5470c6" },
          label: {
            show: true,
            position: "top",
            formatter: (params: any) => {
              const val = params.value;
              return val > 0 ? (val / 100000000).toFixed(0) + "亿" : "";
            },
            fontSize: 10,
          },
        },
      ],
      grid: { left: "10%", right: "10%", bottom: "15%", top: "15%" },
    };
  };

  const getPEChartOption = () => {
    if (!data) return {};

    const sortedData = [...data.yearly_data]
      .filter((d) => d.pe_ratio !== null && d.pe_ratio !== undefined)
      .sort((a, b) => parseInt(a.year) - parseInt(b.year));

    if (sortedData.length === 0) {
      return {
        title: { text: "PE估值 暂无数据", left: "center" },
        textStyle: { color: "#999" },
      };
    }

    return {
      title: {
        text: `${data.company_name} (${data.ticker}) 市盈率(PE)历年变化`,
        left: "center",
      },
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => {
          const item = params[0];
          return `${item.name}<br/>市盈率: ${item.value.toFixed(2)}`;
        },
      },
      xAxis: {
        type: "category",
        data: sortedData.map((d) => d.year),
        name: "年份",
      },
      yAxis: {
        type: "value",
        name: "市盈率 (PE)",
      },
      series: [
        {
          name: "市盈率TTM",
          type: "line",
          data: sortedData.map((d) => d.pe_ratio ?? 0),
          smooth: true,
          lineStyle: { width: 3, color: "#ee6666" },
          itemStyle: { color: "#ee6666" },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(238, 102, 102, 0.3)" },
                { offset: 1, color: "rgba(238, 102, 102, 0.05)" },
              ],
            },
          },
          label: {
            show: true,
            position: "top",
            formatter: (params: any) => params.value.toFixed(1),
            fontSize: 10,
          },
        },
      ],
      grid: { left: "10%", right: "10%", bottom: "15%", top: "15%" },
    };
  };

  const getRevenueGrowthChartOption = () => {
    if (!data) return {};

    const sortedData = [...data.yearly_data].sort(
      (a, b) => parseInt(a.year) - parseInt(b.year)
    );

    const growthData: number[] = [];
    const years: string[] = [];

    for (let i = 1; i < sortedData.length; i++) {
      const current = sortedData[i].revenue ?? 0;
      const previous = sortedData[i - 1].revenue ?? 0;
      if (previous > 0) {
        const growth = ((current - previous) / previous) * 100;
        growthData.push(parseFloat(growth.toFixed(2)));
        years.push(sortedData[i].year);
      }
    }

    return {
      title: {
        text: `${data.company_name} (${data.ticker}) 营收同比增长率`,
        left: "center",
      },
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => {
          const item = params[0];
          const color = item.value >= 0 ? "#5470c6" : "#ef6567";
          return `${item.name}<br/><span style="color:${color}">增长率: ${item.value}%</span>`;
        },
      },
      xAxis: {
        type: "category",
        data: years,
        name: "年份",
      },
      yAxis: {
        type: "value",
        name: "增长率 (%)",
        axisLabel: {
          formatter: (value: number) => `${value}%`,
        },
      },
      series: [
        {
          name: "营收同比增长率",
          type: "bar",
          data: growthData,
          itemStyle: {
            color: (params: any) =>
              params.value >= 0 ? "#5470c6" : "#ef6567",
          },
          label: {
            show: true,
            position: "top",
            formatter: (params: any) => `${params.value}%`,
            fontSize: 9,
          },
        },
      ],
      grid: { left: "10%", right: "10%", bottom: "15%", top: "15%" },
    };
  };

  const getPEBarChartOption = () => {
    if (!data) return {};

    const sortedData = [...data.yearly_data]
      .filter((d) => d.pe_ratio !== null && d.pe_ratio !== undefined)
      .sort((a, b) => parseInt(a.year) - parseInt(b.year));

    if (sortedData.length === 0) {
      return {
        title: { text: "PE估值 暂无数据", left: "center" },
      };
    }

    return {
      title: {
        text: `${data.company_name} (${data.ticker}) 市盈率(PE)分布`,
        left: "center",
      },
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => {
          const item = params[0];
          return `${item.name}<br/>市盈率: ${item.value.toFixed(2)}`;
        },
      },
      xAxis: {
        type: "category",
        data: sortedData.map((d) => d.year),
        name: "年份",
      },
      yAxis: {
        type: "value",
        name: "市盈率 (PE)",
      },
      series: [
        {
          name: "市盈率TTM",
          type: "bar",
          data: sortedData.map((d) => d.pe_ratio ?? 0),
          itemStyle: { color: "#5470c6" },
          label: {
            show: true,
            position: "top",
            formatter: (params: any) => params.value.toFixed(1),
            fontSize: 9,
          },
        },
      ],
      grid: { left: "10%", right: "10%", bottom: "15%", top: "15%" },
    };
  };

  return (
    <main className="page-shell">
      <section className="page-topbar">
        <div>
          <div className="eyebrow">ValueCompass</div>
          <h1 className="page-title">财务历史数据分析</h1>
        </div>
      </section>

      <section className="workspace-shell" style={{ padding: "20px" }}>
        <div className="control-rail">
          <div className="panel control-panel">
            <div className="eyebrow">查询条件</div>
            <div className="form-stack">
              <label className="label">
                <span>股票代码</span>
                <input
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  placeholder="如: 600519"
                  className="input"
                />
              </label>
              <label className="label">
                <span>起始年份</span>
                <input
                  type="text"
                  value={startYear}
                  onChange={(e) => setStartYear(e.target.value)}
                  placeholder="如: 2010"
                  className="input"
                />
              </label>
              <label className="label">
                <span>结束年份</span>
                <input
                  type="text"
                  value={endYear}
                  onChange={(e) => setEndYear(e.target.value)}
                  placeholder="如: 2025"
                  className="input"
                />
              </label>
              <button
                onClick={() => void fetchData()}
                disabled={loading}
                className="button primary"
                style={{ marginTop: "10px" }}
              >
                {loading ? "加载中..." : "查询"}
              </button>
            </div>
          </div>
        </div>

        <div style={{ flex: 1, marginLeft: "280px" }}>
          {error && (
            <div
              style={{
                padding: "15px",
                backgroundColor: "#fee",
                border: "1px solid #f99",
                borderRadius: "8px",
                marginBottom: "20px",
                color: "#c33",
              }}
            >
              {error}
            </div>
          )}

          {data && (
            <>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "20px",
                  marginBottom: "20px",
                }}
              >
                <div className="panel">
                  <h3 style={{ marginBottom: "15px" }}>营业收入树状图</h3>
                  <ReactECharts option={getRevenueChartOption()} style={{ height: "400px" }} />
                </div>
                <div className="panel">
                  <h3 style={{ marginBottom: "15px" }}>市盈率(PE)曲线图</h3>
                  <ReactECharts option={getPEChartOption()} style={{ height: "400px" }} />
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "20px",
                }}
              >
                <div className="panel">
                  <h3 style={{ marginBottom: "15px" }}>营收同比增长率</h3>
                  <ReactECharts
                    option={getRevenueGrowthChartOption()}
                    style={{ height: "400px" }}
                  />
                </div>
                <div className="panel">
                  <h3 style={{ marginBottom: "15px" }}>市盈率(PE)分布</h3>
                  <ReactECharts option={getPEBarChartOption()} style={{ height: "400px" }} />
                </div>
              </div>

              <div className="panel" style={{ marginTop: "20px" }}>
                <h3 style={{ marginBottom: "15px" }}>数据明细</h3>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr
                      style={{
                        borderBottom: "2px solid #ddd",
                        backgroundColor: "#f5f5f5",
                      }}
                    >
                      <th style={tableCellStyle}>年份</th>
                      <th style={tableCellStyle}>营收(亿元)</th>
                      <th style={tableCellStyle}>净利润(亿元)</th>
                      <th style={tableCellStyle}>市盈率(PE)</th>
                      <th style={tableCellStyle}>市净率(PB)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.yearly_data]
                      .sort((a, b) => parseInt(b.year) - parseInt(a.year))
                      .map((item) => (
                        <tr key={item.year} style={{ borderBottom: "1px solid #eee" }}>
                          <td style={tableCellStyle}>{item.year}</td>
                          <td style={tableCellStyle}>
                            {item.revenue
                              ? (item.revenue / 100000000).toFixed(2)
                              : "-"}
                          </td>
                          <td style={tableCellStyle}>
                            {item.net_profit
                              ? (item.net_profit / 100000000).toFixed(2)
                              : "-"}
                          </td>
                          <td style={tableCellStyle}>
                            {item.pe_ratio ? item.pe_ratio.toFixed(2) : "-"}
                          </td>
                          <td style={tableCellStyle}>
                            {item.pb_ratio ? item.pb_ratio.toFixed(2) : "-"}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

const tableCellStyle: React.CSSProperties = {
  padding: "10px",
  textAlign: "right",
  fontSize: "14px",
};