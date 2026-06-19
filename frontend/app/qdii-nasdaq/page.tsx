import QdiiNasdaqClient from "./QdiiNasdaqClient";

export const metadata = {
  title: "QDII 纳指基金 | ValueCompass",
  description: "国内 QDII 纳斯达克基金的申购状态、基金公司和额度看板",
};

export default function QdiiNasdaqPage() {
  return <QdiiNasdaqClient />;
}
