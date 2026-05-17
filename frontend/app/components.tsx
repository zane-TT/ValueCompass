import Link from "next/link";
import type { ReactNode, RefObject } from "react";

type QueryBarProps = {
  stock: string;
  period: string;
  years: string;
  activeCompanyName?: string;
  presets: Array<{ code: string; label: string }>;
  isLoading: boolean;
  combinedError: string;
  onStockChange: (value: string) => void;
  onPeriodChange: (value: string) => void;
  onYearsChange: (value: string) => void;
  onQuery: () => void;
  onPresetSelect: (stock: string) => void;
};

type AutoConclusionItem = {
  label: string;
  value: string;
  detail: string;
  tone?: "positive" | "warning" | "danger" | "neutral";
};

type AutoConclusionStripProps = {
  items: AutoConclusionItem[];
};

type ChartPanelProps = {
  title: string;
  chartRef: RefObject<HTMLDivElement | null>;
  children?: ReactNode;
};

type SectionShellProps = {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
};

type AiAnalysisSectionProps = {
  status: string;
  error?: string | null;
  action: ReactNode;
  children: ReactNode;
};

type SystemStatusProps = {
  action: ReactNode;
  error?: string | null;
  children: ReactNode;
};

type AppShellProps = {
  active: "stocks" | "markets" | "industry";
  children: ReactNode;
};

const NAV_ITEMS = [
  {
    id: "stocks",
    href: "/",
    label: "个股分析",
    eyebrow: "A 股公司",
    initials: "ST",
    enabled: true,
  },
  {
    id: "markets",
    href: "/market-valuation",
    label: "大盘估值",
    eyebrow: "美股指数",
    initials: "PE",
    enabled: true,
  },
  {
    id: "industry",
    href: "/industry-monitor",
    label: "行业监控",
    eyebrow: "利润驱动",
    initials: "ID",
    enabled: true,
  },
  {
    id: "macro",
    href: "#",
    label: "宏观变量",
    eyebrow: "利率 汇率 商品",
    initials: "MA",
    enabled: false,
  },
];

export function AppShell({ active, children }: AppShellProps) {
  return (
    <main className="app-shell">
      <aside className="app-sidebar" aria-label="主导航">
        <Link className="sidebar-brand" href="/">
          <span>VC</span>
          <strong>ValueCompass</strong>
        </Link>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const isActive = item.id === active;
            const className = `sidebar-nav-item ${isActive ? "active" : ""} ${item.enabled ? "" : "disabled"}`;
            const content = (
              <>
                <span className="sidebar-nav-code">{item.initials}</span>
                <span>
                  <strong>{item.label}</strong>
                  <em>{item.eyebrow}</em>
                </span>
              </>
            );

            return item.enabled ? (
              <Link key={item.id} className={className} href={item.href} aria-current={isActive ? "page" : undefined}>
                {content}
              </Link>
            ) : (
              <span key={item.id} className={className} aria-disabled="true">
                {content}
              </span>
            );
          })}
        </nav>

        <div className="sidebar-footnote">
          <span>Data terminal</span>
          <strong>估值、利润驱动、风险变量分层组织</strong>
        </div>
      </aside>

      <section className="app-content">{children}</section>
    </main>
  );
}

export function QueryBar({
  stock,
  period,
  years,
  activeCompanyName,
  presets,
  isLoading,
  combinedError,
  onStockChange,
  onPeriodChange,
  onYearsChange,
  onQuery,
  onPresetSelect,
}: QueryBarProps) {
  return (
    <section className="hero-console">
      <div className="brand-stack">
        <div className="brand-mark">VC</div>
        <div>
          <h1>ValueCompass</h1>
          <p>用财报数据快速判断公司靠什么赚钱、最近几年业绩如何。</p>
        </div>
      </div>

      <div className="query-console">
        <label className="field">
          股票
          <input value={stock} onChange={(event) => onStockChange(event.target.value)} />
        </label>

        <label className="field">
          报告期
          <input
            value={period}
            onChange={(event) => onPeriodChange(event.target.value)}
            placeholder="20241231，可不填"
          />
        </label>

        <label className="field compact-field">
          最近几年
          <input value={years} onChange={(event) => onYearsChange(event.target.value)} />
        </label>

        <button className="query-button" onClick={onQuery}>
          查询
        </button>
      </div>

      {presets.length ? (
        <div className="preset-row">
          {presets.map((item) => (
            <button
              key={item.code}
              type="button"
              className={`preset-button ${stock === item.code ? "active" : ""}`}
              onClick={() => onPresetSelect(item.code)}
            >
              {item.label}
              <span>{item.code}</span>
            </button>
          ))}
        </div>
      ) : null}

      {isLoading ? (
        <div className="status-line">正在加载数据...</div>
      ) : activeCompanyName ? (
        <div className="status-line loaded-company">
          <strong>{activeCompanyName}</strong>
          <span>{stock}</span>
        </div>
      ) : null}
      {combinedError ? <div className="error-box">{combinedError}</div> : null}
    </section>
  );
}

export function AutoConclusionStrip({ items }: AutoConclusionStripProps) {
  return (
    <section className="auto-strip" aria-label="自动结论摘要">
      {items.map((item) => (
        <article key={item.label} className={`auto-cell ${item.tone ?? "neutral"}`}>
          <div className="auto-label">{item.label}</div>
          <div className="auto-value">{item.value}</div>
          <div className="auto-detail">{item.detail}</div>
        </article>
      ))}
    </section>
  );
}

export function ChartPanel({ title, chartRef, children }: ChartPanelProps) {
  return (
    <article className="chart-panel">
      <div className="chart-panel-header">
        <h3>{title}</h3>
      </div>
      <div ref={chartRef} className="chart-box compact-chart" />
      {children}
    </article>
  );
}

export function SectionShell({ title, description, action, meta, children, className = "" }: SectionShellProps) {
  return (
    <section className={`section-shell ${className}`}>
      <div className="section-header">
        <div>
          <h2>{title}</h2>
          {description ? <div className="subtle">{description}</div> : null}
        </div>
        <div className="section-actions">
          {meta ? <div className="section-meta">{meta}</div> : null}
          {action}
        </div>
      </div>
      {children}
    </section>
  );
}

export function BusinessModelSection(props: Omit<SectionShellProps, "className">) {
  return <SectionShell {...props} className="business-section" />;
}

export function AiAnalysisSection({ status, error, action, children }: AiAnalysisSectionProps) {
  return (
    <SectionShell
      title="OpenAI 财报综合分析"
      description="结合资产负债、营收、市值、净利润和市盈率做整体解读，并自动判断商业模式类型。"
      action={action}
      className="ai-section"
    >
      <div className="status">{status}</div>
      {error ? <div className="error-box">{error}</div> : null}
      {children}
    </SectionShell>
  );
}

export function SystemStatus({ action, error, children }: SystemStatusProps) {
  return (
    <SectionShell
      title="系统状态"
      description="后端在线状态、缓存文件和运行时长。"
      action={action}
      className="system-section"
    >
      {error ? <div className="error-box">{error}</div> : null}
      {children}
    </SectionShell>
  );
}

export type { AutoConclusionItem };
