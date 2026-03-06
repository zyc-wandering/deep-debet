# AGENTS.md

## Project Overview

This repository contains `DebateAI Room`, a local MVP for multi-agent AI debate:

- Frontend: React + TypeScript + Vite + Zustand
- Backend: FastAPI + async orchestrator
- Streaming: SSE from backend to frontend
- Storage: local files under `data/reports` and `data/sessions`

The app takes a topic, generates multiple debate personas, streams a debate, and writes a markdown report locally.

## Repository Layout

- `backend/app/main.py`: FastAPI entrypoints
- `backend/app/orchestrator.py`: end-to-end debate flow
- `backend/app/agents/host_agent.py`: topic research, persona generation, summary
- `backend/app/agents/debater_agent.py`: per-debater prompting and fallback logic
- `backend/app/agents/context_manager.py`: rolling context construction for debaters
- `backend/app/providers/llm_openai_compat.py`: OpenAI-compatible provider wrapper
- `backend/app/config.py`: provider selection and local key/env loading
- `frontend/src/pages/DebatePage.tsx`: main UI
- `frontend/src/hooks/useDebate.ts`: SSE client logic
- `frontend/src/store/debateStore.ts`: frontend debate state
- `data/reports/`: generated markdown reports
- `data/sessions/`: persisted session snapshots

## Run Commands

Prefer starting the backend from the repository root so paths resolve consistently.

### Backend

```powershell
cd D:\projects\debet_room_codex
.\backend\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

If the virtualenv does not exist yet:

```powershell
cd D:\projects\debet_room_codex\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### Frontend

```powershell
cd D:\projects\debet_room_codex\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

## Validation Commands

### Backend tests

```powershell
cd D:\projects\debet_room_codex\backend
.\.venv\Scripts\python -m pytest
```

### Frontend build

```powershell
cd D:\projects\debet_room_codex\frontend
npm run build
```

### Health check

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health
```

## Provider Notes

- This project currently supports OpenAI-compatible chat completion providers.
- `backend/app/config.py` prefers local key loading in this order:
  - `OPENAI_API_KEY`
  - `ARK_API_KEY` / `SEED_API_KEY`
  - `MOONSHOT_API_KEY`
  - local `keys.ts`
- Current Volcengine Ark integration uses:
  - base URL: `https://ark.cn-beijing.volces.com/api/v3`
  - model: `doubao-seed-2-0-lite-260215`

## Important Project-Specific Rules

- Do not commit real API keys. `keys.ts` is local-only and ignored.
- Do not commit generated runtime reports or session JSONs beyond the existing `.gitkeep` files.
- Keep debate prompts professional. Do not reintroduce hardcoded topic-specific fallback rhetoric.
- Debate personas should differ by incentives, analysis frame, or institutional position, not by gratuitous insults.
- Preserve the current timing behavior: the debate timer starts after `debaters_ready`, not during host preparation.
- When changing debate quality, inspect both:
  - prompt design in `host_agent.py` and `debater_agent.py`
  - context assembly in `context_manager.py`

## Known Quality Targets

- Debaters should reference other speakers' arguments, not just repeat their own stance.
- Disagreement should be substantive, not pure shouting.
- Partial agreement on side issues is acceptable and desirable.
- Reports should summarize core disagreements, evidence, and conditional judgments.

## When Editing

- Use `apply_patch` for manual file edits.
- Prefer minimal, targeted changes.
- If you modify prompting or context behavior, run backend tests and at least one live local debate before concluding the task.
