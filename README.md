# DebateAI Room (MVP)

Multi-agent AI debate app for exploring a topic from competing perspectives.

## Stack

- Frontend: React + TypeScript + Vite + Zustand + SSE client
- Backend: FastAPI + async orchestrator + OpenAI-compatible LLM provider + Tavily search
- Storage: local files (`data/reports`, `data/sessions`)

## Quick Start

1. Copy env template:

```bash
cp .env.example .env
```

2. Backend:

```bash
cd backend
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If `python` is unavailable on your PATH, use `uv`:

```bash
uv run --with-requirements backend/requirements.txt uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

3. Frontend (new terminal):

```bash
cd frontend
npm install
npm run dev
```

4. Open `http://localhost:5173`.

## API

- `POST /api/debate/start` -> SSE stream
- `POST /api/debate/stop` -> stop active session
- `GET /api/debate/report?path=...` -> read generated markdown report
- `GET /api/health`

## Notes

- `OPENAI_BASE_URL` can point to any OpenAI-compatible endpoint (including Kimi-compatible gateways).
- Do **not** commit real API keys.
- Reports are generated under `data/reports/`.

## Architecture Docs

- `docs/agentic-harness-architecture.md`: reference architecture for a two-sandbox agentic harness workflow with human review gates and Mermaid diagrams
- `docs/agentic-harness-technical-design.md`: technical design covering OpenSandbox, LangGraph, tool permissions, core components, and GitHub Actions workflows
