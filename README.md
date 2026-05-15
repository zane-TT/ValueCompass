<p align="center">
  <h1 align="center">ValueCompass</h1>
  <p align="center">
    Turn A-share financial statements into clear, interactive research signals.
  </p>
</p>

<p align="center">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi">
  <img alt="ECharts" src="https://img.shields.io/badge/ECharts-Visualization-AA344D">
  <img alt="License" src="https://img.shields.io/badge/license-Learning%20Project-blue">
</p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#api-examples">API</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

ValueCompass is an open-source financial statement analysis workspace for China A-share companies. It helps answer one question faster:

> Is this company really making high-quality money?

It turns public financial data into interactive charts, business breakdowns, cash-flow quality checks, valuation views, and peer-company comparisons.

## Features

| Area | Status | Description |
| --- | --- | --- |
| Revenue & Market Cap | Available | Compare revenue scale with market valuation. |
| Net Profit & Market Cap | Available | View earnings and valuation in raw values. |
| Cash Flow Quality | Available | Compare operating cash flow, net profit, and cash-to-profit ratio. |
| Balance Sheet Structure | Available | Visualize assets, liabilities, cash, receivables, inventory, and debt. |
| Business Breakdown | Available | Break down revenue by product, industry, region, and channel. |
| Peer Companies | Available | Recommend comparable companies from business keywords. |
| AI Analysis | Optional | Generate financial summaries with an OpenAI-compatible API. |

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
