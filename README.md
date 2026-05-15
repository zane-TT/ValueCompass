# ValueCompass

ValueCompass 是一个面向 A 股公司的财报分析工作台。它把公开财务数据转成可交互图表，帮助用户快速理解一家公司靠什么赚钱、业绩怎么变、利润质量如何，以及市场定价是否和基本面匹配。

ValueCompass is a financial statement analysis workspace for China A-share companies. It turns public financial data into interactive charts, helping users quickly understand how a company makes money, how its performance changes, whether profits are backed by cash flow, and whether market valuation matches fundamentals.

## 功能 / Features

- 营收、市值、净利润、现金流、市盈率等图表分析
- 按产品、行业、地区、渠道拆解主营业务
- 现金流与盈利质量判断
- 资产负债结构可视化
- 同行竞品推荐
- OpenAI-compatible 财报综合分析

- Revenue, market cap, net profit, cash flow, and PE trend charts
- Business breakdown by product, industry, region, and channel
- Cash flow and earnings quality analysis
- Balance sheet structure visualization
- Peer company recommendations
- OpenAI-compatible financial analysis

## 技术栈 / Tech Stack

- Frontend: Next.js, React, ECharts
- Backend: FastAPI, AKShare, pandas
- AI: OpenAI-compatible API

## 快速开始 / Quick Start

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python app.py
```

后端默认运行在 / Backend runs at:

```text
http://127.0.0.1:5001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 / Frontend runs at:

```text
http://127.0.0.1:3000
```

### 单服务模式 / Single-Server Mode

先构建前端，再启动后端。FastAPI 会同时托管前端静态文件和 `/api/*`。

Build the frontend first, then start the backend. FastAPI will serve both the frontend files and `/api/*`.

```bash
cd frontend
npm install
npm run build

cd ../backend
python -m pip install -r requirements.txt
python app.py
```

打开 / Open:

```text
http://127.0.0.1:5001
```

## 环境变量 / Environment

复制 `backend/.env.example` 并配置 OpenAI-compatible API。

Copy `backend/.env.example` and configure your OpenAI-compatible API settings:

```text
OPENAI_BASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TEMPERATURE=0.1
```

AI 分析是可选功能。没有 API key 时，财务图表仍然可以使用。

AI analysis is optional. The financial charts can run without an API key.

## API 示例 / API Examples

```text
GET /api/revenue-market-cap?stock=600519&years=8
GET /api/profit-market-cap?stock=600519&years=8
GET /api/cash-flow-quality?stock=600519&years=8
GET /api/revenue-structure?stock=600519&years=8
GET /api/peer-companies?stock=600519&limit=6
GET /api/pe-trend?stock=600519&years=8
POST /api/ai-analysis
```

## 项目结构 / Project Structure

```text
backend/   FastAPI 后端与数据处理 / FastAPI backend and data processing
frontend/  Next.js 前端与图表工作区 / Next.js frontend and chart workspace
docs/      路线图与实现笔记 / Roadmap and implementation notes
```

## 免责声明 / Disclaimer

ValueCompass 仅用于学习、研究和数据可视化展示，不构成任何投资建议。财务数据可能存在延迟、缺失或口径差异，使用前请自行核验。

ValueCompass is for learning, research, and data visualization only. It is not investment advice. Financial data may be delayed, incomplete, or inconsistent across sources.
