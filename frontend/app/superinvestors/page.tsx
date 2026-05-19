import SuperinvestorsClient from "./SuperinvestorsClient";

export const metadata = {
  title: "超级投资者 | ValueCompass",
  description: "基于 DATAROMA 公开页面的超级投资者持仓更新、集中买入和内部人买入观察。",
};

export default function SuperinvestorsPage() {
  return <SuperinvestorsClient />;
}
