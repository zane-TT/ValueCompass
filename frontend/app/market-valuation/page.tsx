import MarketValuationClient from "./MarketValuationClient";

export const metadata = {
  title: "大盘估值 | ValueCompass",
  description: "标普500、纳斯达克100等大盘指数的 PE 历史分位和利率对比",
};

export default function MarketValuationPage() {
  return <MarketValuationClient />;
}
