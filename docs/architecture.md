# Architecture

## Target stack

- Frontend: Next.js App Router + TypeScript
- Backend: FastAPI + Pydantic

## Analysis pipeline

### 1. Data Agent

- ingest annual / quarterly statement payloads
- normalize metrics
- derive helper ratios

### 2. Quality Agent

- identify balance sheet and cash flow red flags
- score financial quality
- explain risk indicators

### 3. Valuation Agent

- choose valuation lens by industry family
- interpret PE / PB / ROE / dividend and cash profile
- produce valuation stance and safety margin commentary

### 4. Thesis Agent

- synthesize business quality, valuation, and risks
- create memo sections
- surface falsification points

### 5. Review Agent

Planned next step:

- track holdings
- compare thesis vs actual updates
- create sell / trim reminders
