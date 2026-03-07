# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DebateAI Room is a multi-agent AI debate application that explores topics from competing perspectives. It features a React frontend and FastAPI backend with an async orchestrator that manages LLM-powered debaters.

## Development Commands

### Backend (FastAPI + Python)

```powershell
# Setup
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Or using uv (if python unavailable on PATH)
uv run --with-requirements backend/requirements.txt uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Run tests
cd backend
pytest
```

### Frontend (React + TypeScript + Vite)

```powershell
cd frontend
npm install
npm run dev      # Development server at http://localhost:5173
npm run build    # Production build
npm run preview  # Preview production build
```

### Environment Configuration

Copy `.env.example` to `.env` and configure:
- `OPENAI_API_KEY` or provider-specific keys (`ARK_API_KEY`, `MOONSHOT_API_KEY`, `SEED_API_KEY`)
- `OPENAI_BASE_URL` - any OpenAI-compatible endpoint
- `TAVILY_API_KEY` - for search functionality

Optional: Create `backend/keys.ts` as a fallback key source (see `config.py` for format).

## Architecture

### Backend Structure

**Core Flow (`app/orchestrator.py`):**
The `DebateOrchestrator` manages the debate lifecycle through phases:
1. `booting` - Initialize session
2. `researching` - HostAgent researches topic via Tavily search
3. `assembling` - HostAgent generates debater configs (2-5 debaters with distinct stances)
4. `debating` - DebaterAgents take turns producing arguments
5. `summarizing` - HostAgent generates final markdown report

**Key Components:**
- `app/agents/host_agent.py` - Researches topics, creates debater configs, summarizes debates
- `app/agents/debater_agent.py` - Produces debate turns with contextual awareness
- `app/agents/context_manager.py` - Builds rolling summaries and context windows
- `app/providers/llm_openai_compat.py` - OpenAI-compatible LLM provider with auto-detection for Ark/Seed, Kimi, Moonshot
- `app/providers/search_tavily.py` - Tavily search integration
- `app/storage/session_store.py` - In-memory session state management
- `app/storage/report_writer.py` - Markdown report generation to `data/reports/`

**Provider Auto-Detection (`app/config.py`):**
The config automatically detects provider from API key format:
- `sk-kimi-*` → Kimi Code API
- Moonshot format → Moonshot Open Platform
- UUID format → Ark/Seed API

### Frontend Structure

**State Management (`src/store/debateStore.ts`):**
Zustand store manages:
- Debate phase and workflow activities
- Live token buffers for streaming display
- Debater configurations and debate lines
- Report markdown

**API Integration (`src/hooks/useDebate.ts`):**
Uses `@microsoft/fetch-event-source` for SSE streaming from `/api/debate/start`. Handles events:
- `phase` - Phase transitions
- `host_research` - Research output stream
- `debaters_ready` - Debater configs received
- `debate_token` - Live token streaming
- `debate_turn_end` - Turn completion
- `host_summary` - Summary stream
- `done` - Debate complete with report path

**Key Components:**
- `DebatePage` - Main debate interface
- `DebateStream` - Real-time debate display
- `WorkflowPanel` - Phase visualization
- `ReportView` - Markdown report rendering
- `TopicInput` - Debate configuration form

### API Endpoints

- `POST /api/debate/start` - SSE stream for debate execution
- `POST /api/debate/stop` - Request early termination
- `GET /api/debate/report?path=...` - Retrieve generated report
- `GET /api/health` - Service health check

### Data Flow

1. User submits topic → `DebateStartRequest`
2. HostAgent searches Tavily → generates research brief
3. HostAgent generates `DebaterConfig[]` with distinct personas
4. For each turn: DebaterAgent builds context → LLM call → token streaming
5. Debate ends (time limit, max turns, or stop request) → HostAgent summarizes
6. Report written to `data/reports/{timestamp}-{sanitized_topic}.md`

### Key Design Patterns

- **Provider Pattern**: `LLMProvider` and `SearchProvider` abstractions allow swapping implementations
- **Agent Pattern**: Host and Debater agents encapsulate role-specific prompting
- **Context Management**: Rolling summaries prevent context overflow in long debates
- **Fallback Systems**: All agents have fallback responses if LLM calls fail
- **Streaming Architecture**: SSE events stream tokens for real-time UI updates
