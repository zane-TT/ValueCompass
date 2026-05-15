# ValueCompass

ValueCompass 是一个面向 A 股公司的财报分析工作台。它把公开财务数据转成可交互图表，帮助用户快速理解一家公司靠什么赚钱、业绩怎么变、利润质量如何，以及市场定价是否和基本面匹配。

## Features

- 营收、市值、净利润、现金流、市盈率等图表分析
- 按产品、行业、地区、渠道拆解主营业务
- 现金流与盈利质量判断
- 资产负债结构可视化
- 同行竞品推荐
- OpenAI-compatible 财报综合分析

## Tech Stack

- Frontend: Next.js, React, ECharts
- Backend: FastAPI, AKShare, pandas
- AI: OpenAI-compatible API

## Quick Start

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python app.py
```

Backend runs at:

```text
http://127.0.0.1:5001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:

```text
http://127.0.0.1:3000
```

### Single-Server Mode

Build the frontend first, then start the backend. FastAPI will serve both the frontend files and `/api/*`.

```bash
cd frontend
npm install
npm run build

cd ../backend
python -m pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5001
```

## Environment

Copy `backend/.env.example` and configure your OpenAI-compatible API settings:

```text
OPENAI_BASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TEMPERATURE=0.1
```

AI analysis is optional. The financial charts can run without an API key.

## API Examples

```text
GET /api/revenue-market-cap?stock=600519&years=8
GET /api/profit-market-cap?stock=600519&years=8
GET /api/cash-flow-quality?stock=600519&years=8
GET /api/revenue-structure?stock=600519&years=8
GET /api/peer-companies?stock=600519&limit=6
GET /api/pe-trend?stock=600519&years=8
POST /api/ai-analysis
```

## Project Structure

```text
backend/   FastAPI backend and data processing
frontend/  Next.js frontend and chart workspace
docs/      Roadmap and implementation notes
```

## Disclaimer

ValueCompass is for learning, research, and data visualization only. It is not investment advice. Financial data may be delayed, incomplete, or inconsistent across sources.
