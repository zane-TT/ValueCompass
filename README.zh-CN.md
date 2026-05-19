<h1 align="center">ValueCompass</h1>

<p align="center">
  把 A 股财报数据转成清晰、可交互的研究信号。
</p>

<p align="center">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs">
  <img alt="React" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=111">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi">
  <img alt="ECharts" src="https://img.shields.io/badge/ECharts-Visualization-AA344D">
  <img alt="License" src="https://img.shields.io/badge/license-Learning%20Project-blue">
</p>

<p align="center">
  <a href="#为什么做-valuecompass">为什么</a> /
  <a href="#界面截图">截图</a> /
  <a href="#功能">功能</a> /
  <a href="#快速开始">快速开始</a> /
  <a href="#api">API</a> /
  <a href="https://valuecompass.onrender.com/">在线预览</a> /
  <a href="./README.md">English</a>
</p>

ValueCompass 是一个面向 A 股公司的开源可视化研究仪表盘，用公开财务数据帮助用户快速判断公司质量、估值位置和利润驱动因素。

它的核心目标，是更快回答一个问题：

> 这家公司赚的钱，质量到底怎么样？

它把公开财务数据转成可交互图表、业务拆解、现金流质量判断、估值观察、同业对比和可选 AI 解读，帮助用户快速形成对一家公司的第一层判断。

在线预览：[valuecompass.onrender.com](https://valuecompass.onrender.com/)

## 为什么做 ValueCompass

财报信息很密，但真正做研究时，经常先想快速确认几个问题：

- 营收和利润是否持续增长，市场是否已经给了很高定价？
- 净利润有没有经营现金流支撑？
- 资产负债表里现金、应收、存货、债务等关键项目是否健康？
- 公司的收入来自哪些产品、地区或业务线？
- 当前估值相对历史区间和大盘环境处在什么位置？

ValueCompass 希望把这些问题变成可以直接阅读和比较的研究模块。

## 界面截图

### 个股分析

把营收、利润、现金流质量和估值历史放在同一屏，帮助用户更快完成一家公司的第一轮阅读。

![个股分析仪表盘](docs/screenshots/company-analysis.png)

### 大盘估值

把主要指数 PE、历史分位和 10Y 利率放在一起，为个股估值判断提供市场背景。

![大盘估值仪表盘](docs/screenshots/market-valuation.png)

## 功能

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 营收与市值 | 已支持 | 对比收入规模和市场定价趋势。 |
| 净利润与市值 | 已支持 | 观察盈利增长和市值变化。 |
| 现金流与盈利质量 | 已支持 | 对比经营现金流、归母净利润和净现比。 |
| 资产负债结构 | 已支持 | 拆解现金、应收、存货、负债等关键科目。 |
| 业务结构拆解 | 已支持 | 按产品、行业、地区、渠道理解收入来源。 |
| 同行竞品推荐 | 已支持 | 根据主营业务关键词推荐可比公司。 |
| 利润驱动模型 | 实验中 | 把业务分部与商品价格、销量、成本等驱动项连接起来。 |
| 大盘估值 | 已支持 | 查看主要指数 PE 分位、历史区间和 10Y 利率对比。 |
| AI 财报分析 | 可选 | 接入 OpenAI-compatible API 生成结构化解读。 |

## 技术栈

- 前端：Next.js 15、React 19、ECharts
- 后端：FastAPI、AKShare、pandas
- AI：OpenAI-compatible API
- 部署：FastAPI 单入口托管前端静态文件和 `/api/*`

## 快速开始

推荐运行环境：

- Python 3.12+
- Node.js 20+

### 1. 启动后端

```bash
cd backend
python -m pip install -r requirements.txt
python app.py
```

后端默认运行在：

```text
http://127.0.0.1:5001
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在：

```text
http://127.0.0.1:3000
```

本地开发时，前端会请求 `http://127.0.0.1:5001` 的后端 API。

### 3. 单服务模式

先构建前端，再启动后端。FastAPI 会同时托管前端静态文件和 `/api/*`。

```bash
cd frontend
npm install
npm run build

cd ../backend
python -m pip install -r requirements.txt
python app.py
```

打开：

```text
http://127.0.0.1:5001
```

## 环境变量

复制 `backend/.env.example` 为 `backend/.env`，然后配置 OpenAI-compatible API：

```text
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=your_model
OPENAI_TEMPERATURE=0.1
```

AI 分析是可选功能，可以接入 OpenAI 或任何 OpenAI-compatible endpoint。没有 API key 时，财务图表和估值仪表盘仍然可以使用。

## API

常用接口：

```text
GET  /api/health
GET  /api/dashboard-data?stock=600519&years=8
GET  /api/revenue-market-cap?stock=600519&years=8
GET  /api/profit-market-cap?stock=600519&years=8
GET  /api/cash-flow-quality?stock=600519&years=8
GET  /api/balance?stock=600519
GET  /api/revenue-structure?stock=600519&years=8
GET  /api/peer-companies?stock=600519&limit=6
GET  /api/pe-trend?stock=600519&years=8
GET  /api/market-index-valuation?index=sp500&years=5
POST /api/ai-analysis
POST /api/business-type-analysis
```

完整交互式 API 文档：

```text
http://127.0.0.1:5001/docs
```

## 项目结构

```text
backend/              FastAPI 后端、数据处理和 API 缓存
frontend/             Next.js 前端和 ECharts 仪表盘
docs/                 路线图、说明文档和 README 截图
docs/screenshots/     README 使用的产品截图
render.yaml           Render 部署配置
```

## 说明

- 数据来自公开来源，可能存在延迟、缺失或口径差异。
- `backend/cache/` 用于加速本地重复分析。
- 这是学习和研究项目，不是交易系统。

## Roadmap

- 增加更多行业分析模板。
- 扩展商品、制造、消费等业务的利润驱动模型。
- 支持导出研究快照。
- 改进数据源 fallback 和数据新鲜度检查。
- 增加英文 UI 模式。

## 免责声明

ValueCompass 仅用于学习、研究和数据可视化展示，不构成任何投资建议。做出投资决策前，请自行核验相关财务数据。
