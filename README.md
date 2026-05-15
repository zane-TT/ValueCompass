# ValueCompass

ValueCompass 是一个面向 A 股公司的财报分析工作台。它基于 AKShare 获取公开财务数据，通过 Next.js、ECharts 和 FastAPI 将财报指标转成可交互图表，并自动生成业务结构、盈利质量、估值区间和风险提示。

项目目标不是替代专业投研系统，而是帮助用户在几分钟内形成对一家公司的第一层判断：它靠什么赚钱、赚得是否稳定、利润是否有现金流支撑，以及市场给它的估值是否和业绩变化匹配。

## 为什么做这个项目

很多财报数据是公开的，但原始表格不容易直接形成判断。ValueCompass 尝试把“财报科目”翻译成更接近业务理解的问题：

- 公司主要收入来自哪些产品、行业、地区或渠道？
- 营收、净利润和市值变化是否同步？
- 利润有没有变成经营现金流？
- 资产负债结构里有哪些需要重点关注的科目？
- 这家公司应该和哪些同行放在一起比较？

## 核心功能

- 多图表工作区：自由选择营收、市值、净利润、现金流、资产负债、市盈率等图表。
- 公司业务拆解：按产品、行业、地区、渠道理解公司收入来源。
- 现金流与盈利质量：对比经营现金流、归母净利润和净现比。
- 净利润与市值对比：观察业绩变化和市场定价是否同步。
- 资产负债结构：拆解现金、应收、存货、负债等关键科目。
- 同行竞品推荐：根据主营业务和行业关键词推荐可对比公司。
- AI 财报分析：接入 OpenAI-compatible API 生成综合解读。

## 技术栈

- Frontend：Next.js、React、ECharts
- Backend：FastAPI、AKShare、pandas
- AI：OpenAI-compatible API
- Data：A 股公开财务数据

## 快速开始

### 生产式单入口启动

先构建前端静态产物，再启动 FastAPI。启动后只需要访问一个地址，FastAPI 会同时返回前端页面、前端静态资源和后端 `/api/*`。

```powershell
cd D:\github\ValueCompass\frontend
npm install
npm run build

cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe -m pip install -r requirements.txt
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

启动后访问：

```text
http://127.0.0.1:5001
```

路由说明：

```text
/              前端页面
/_next/...     前端静态资源
/api/...       后端 API
/docs          FastAPI 自动接口文档
```

### 开发模式

开发时可以分开启动，前端支持热更新，后端仍然跑在 `5001`。

后端：

```powershell
cd D:\github\ValueCompass\backend
D:\github\ValueCompass\.venv312\Scripts\python.exe -m pip install -r requirements.txt
D:\github\ValueCompass\.venv312\Scripts\python.exe app.py
```

前端：

```powershell
cd D:\github\ValueCompass\frontend
npm install
npm run dev
```

开发地址：

```text
http://127.0.0.1:3000
```

## OpenAI 配置

后端通过环境变量读取 OpenAI 配置。可以参考 [backend/.env.example](backend/.env.example)。

```text
OPENAI_BASE_URL=https://api.openai-proxy.org/v1
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-nano-2026-03-17
OPENAI_TEMPERATURE=0.1
```

说明：

- 真实 API key 不应写入仓库。
- 如果没有配置 `OPENAI_API_KEY`，后端会返回清晰错误信息。

## API 示例

```text
GET /api/revenue-market-cap?stock=600519&years=8
GET /api/profit-market-cap?stock=600519&years=8
GET /api/cash-flow-quality?stock=600519&years=8
GET /api/revenue-structure?stock=600519&years=8
GET /api/peer-companies?stock=600519&limit=6
GET /api/pe-trend?stock=600519&years=8
POST /api/ai-analysis
```

AI 分析请求体：

```json
{
  "stock": "600519",
  "period": null,
  "years": 8
}
```

## 项目结构

```text
backend/
  app.py                 FastAPI 后端入口与数据处理逻辑
  requirements.txt       Python 依赖
  .env.example           OpenAI 配置示例

frontend/
  app/page.tsx           主页面和图表逻辑
  app/components.tsx     页面组件
  app/globals.css        全局样式

docs/
  roadmap-next-steps.md  后续路线图
```

## Roadmap

近期优先方向见 [docs/roadmap-next-steps.md](docs/roadmap-next-steps.md)：

- 现金流与盈利质量分析
- 同比 / TTM 业绩摘要
- 自动风险提示模块
- 更稳定的同行竞品识别
- 更清晰的图表工作区交互

## 免责声明

ValueCompass 仅用于学习、研究和数据可视化展示，不构成任何投资建议。财务数据来自公开数据源，可能存在延迟、缺失或口径差异，使用前请自行核验。
