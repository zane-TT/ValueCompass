<p align="center">
  <h1 align="center">ValueCompass</h1>
  <p align="center">
    把 A 股财报数据转成清晰、可交互的研究信号。
  </p>
</p>

<p align="center">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi">
  <img alt="ECharts" src="https://img.shields.io/badge/ECharts-Visualization-AA344D">
  <img alt="License" src="https://img.shields.io/badge/license-Learning%20Project-blue">
</p>

<p align="center">
  <a href="#功能">功能</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#api-示例">API</a> ·
  <a href="./README.md">English</a>
</p>

ValueCompass 是一个面向 A 股公司的开源财报分析工作台，用来更快回答一个问题：

> 这家公司赚的钱，质量到底怎么样？

它把公开财务数据转成可交互图表、业务拆解、现金流质量判断、估值观察和同行对比，帮助用户快速形成对一家公司的第一层判断。

## 功能

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 营收与市值 | 已支持 | 对比收入规模和市场定价。 |
| 净利润与市值 | 已支持 | 用原始金额观察盈利和市值变化。 |
| 现金流与盈利质量 | 已支持 | 对比经营现金流、归母净利润和净现比。 |
| 资产负债结构 | 已支持 | 拆解现金、应收、存货、负债等关键科目。 |
| 业务结构拆解 | 已支持 | 按产品、行业、地区、渠道理解收入来源。 |
| 同行竞品推荐 | 已支持 | 根据主营业务关键词推荐可对比公司。 |
| AI 财报分析 | 可选 | 接入 OpenAI-compatible API 生成综合解读。 |

## 技术栈

- 前端：Next.js、React、ECharts
- 后端：FastAPI、AKShare、pandas
- AI：OpenAI-compatible API

## 快速开始

### 后端

```bash
cd backend
python -m pip install -r requirements.txt
python app.py
```

后端默认运行在：

```text
http://127.0.0.1:5001
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在：

```text
http://127.0.0.1:3000
```

### 单服务模式

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

复制 `backend/.env.example` 并配置 OpenAI-compatible API：

```text
OPENAI_BASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TEMPERATURE=0.1
```

AI 分析是可选功能。没有 API key 时，财务图表仍然可以使用。

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

## 项目结构

```text
backend/   FastAPI 后端与数据处理
frontend/  Next.js 前端与图表工作区
docs/      路线图与实现笔记
```

## 免责声明

ValueCompass 仅用于学习、研究和数据可视化展示，不构成任何投资建议。财务数据可能存在延迟、缺失或口径差异，使用前请自行核验。
