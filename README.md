# Equity Research Agent MVP

An MVP for a stock research AI agent using:

- `Next.js` for the frontend and server-rendered UI
- `FastAPI` for the backend analysis pipeline

## MVP features

- Read annual / quarterly statement data and normalize key metrics
- Detect financial quality risks
- Produce industry-aware valuation commentary
- Generate an investment memo:
  - thesis
  - valuation
  - risks
  - falsification points

## Project structure

- `frontend/` Next.js app
- `backend/` FastAPI service
- `docs/` architecture notes

## Run locally

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Or run the PyCharm-friendly startup script:

```bash
cd backend
python run_server.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Frontend expects the backend at `http://localhost:8000`.

## Current MVP scope

This version includes a sample dataset and deterministic analysis logic so the
full product flow is usable before live data connectors are added.

## LangChain + OpenAI demo

This repo also includes a backend demo that shows how to package atomic
capabilities as tools and let an OpenAI model decide when to call them.

- doc: `docs/langchain-openai-demo.md`
- route: `POST /agent-demo`
- core files:
  - `backend/app/langchain_tools.py`
  - `backend/app/langchain_demo.py`
