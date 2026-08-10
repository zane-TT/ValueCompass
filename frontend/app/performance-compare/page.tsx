import PerformanceCompareClient from "./PerformanceCompareClient";

export const metadata = {
  title: "业绩对比 | ValueCompass",
  description: "把多家 A 股公司的同一财务指标放到同一张图里比较。",
};

export default function PerformanceComparePage() {
  return <PerformanceCompareClient />;
}
