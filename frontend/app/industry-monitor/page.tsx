import IndustryMonitorClient from "./IndustryMonitorClient";

export const metadata = {
  title: "行业监控 | ValueCompass",
  description: "按公司和行业模块查看经营环境、进出口、能源成本和行业专项指标。",
};

export default function IndustryMonitorPage() {
  return <IndustryMonitorClient />;
}
