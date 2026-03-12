# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DebateAI Room is a multi-agent AI debate application that explores topics from competing perspectives. It features a React frontend and FastAPI backend with an async orchestrator that manages LLM-powered debaters through structured debate stages.

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
pytest                    # Run all tests
pytest tests/test_orchestrator.py -v    # Run single test file
pytest tests/ -k test_name              # Run specific test by name
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
- `DEFAULT_DEBATER_COUNT`, `DEFAULT_TIME_LIMIT_SEC`, `DEFAULT_MAX_TURNS` - debate defaults

Optional: Create `backend/keys.ts` as a fallback key source (see `config.py` for format).

## Architecture

### Backend Structure

**Phase-Based Flow (`app/orchestrator.py`):**
The `DebateOrchestrator` manages the debate lifecycle in two main phases:
1. `start()` - Research phase: HostAgent researches topic, generates focus options, pauses for user selection
2. `configure()` - Debate phase: After user selects focus/intensity, runs debate stages and generates report

**Debate Stages (`app/stage/`):**
The debate execution uses a stage pipeline pattern:
- `OpeningStageExecutor` - Debaters present opening statements
- `FreeDebateStageExecutor` - Turn-based back-and-forth debate (main discussion)
- `ClosingStageExecutor` - Debaters present closing statements
- `SummaryStageExecutor` - Host generates structured report

Stages are registered in `StageRegistry` and executed sequentially via `_execute_debate_stages()`.

**Key Components:**
- `app/agents/host_agent.py` - Researches topics, creates debater configs, summarizes debates, handles follow-ups
- `app/agents/debater_agent.py` - Produces debate turns with contextual awareness and search capabilities
- `app/agents/context_manager.py` - Builds rolling summaries and context windows
- `app/execution/turn_executor.py` - Executes individual debater turns with timing and streaming
- `app/providers/llm_openai_compat.py` - OpenAI-compatible LLM provider with auto-detection
- `app/providers/search_tavily.py` - Tavily search integration
- `app/providers/image_generation.py` - Avatar and background image generation
- `app/storage/session_store.py` - In-memory session state management
- `app/storage/report_writer.py` - Markdown report generation to `data/reports/`

**Provider Auto-Detection (`app/config.py`):**
The config automatically detects provider from API key format:
- `sk-kimi-*` → Kimi Code API
- Moonshot format → Moonshot Open Platform
- UUID format → Ark/Seed API

**Model Variants:**
- `lite` - Uses standard model (default: gpt-4.1-mini)
- `pro` - Uses enhanced model with web search tool support

### Frontend Structure

**State Management (`src/store/debateStore.ts`):**
Zustand store manages:
- Debate phase and workflow activities
- Live token buffers for streaming display
- Debater configurations and debate lines
- Report markdown and session state
- Focus selection and pre-debate configuration

**API Integration (`src/hooks/useDebate.ts`):**
Uses `@microsoft/fetch-event-source` for SSE streaming. Handles events:
- `phase` - Phase transitions (booting, researching, configuring, assembling, opening, free_debate, closing, summarizing)
- `host_research` - Research output stream
- `focus_options_ready` - Focus selection options from host
- `debaters_ready` - Debater configs received
- `debate_token` - Live token streaming
- `debate_turn_end` - Turn completion
- `background_ready`, `avatars_ready` - Image generation completion
- `host_summary` - Summary stream
- `done` - Debate complete with report path

**Stage-Based UI (`src/stages/`):**
The frontend uses a stage-based component system:
- `ConfigStage` - Topic input and initial configuration
- `ResearchStage` - Shows host research and focus selection
- `DebateStage` - Live debate display with timer and debater cards
- `ReportStage` - Final report and follow-up Q&A

### API Endpoints

- `POST /api/debate/start` - SSE stream for debate research phase
- `POST /api/debate/configure` - SSE stream for debate execution phase (after focus selection)
- `POST /api/debate/stop` - Request early termination
- `POST /api/debate/followup` - Post-debate Q&A with host or debater
- `GET /api/debate/report?path=...` - Retrieve generated report
- `GET /api/images/{filename}` - Serve generated avatars/backgrounds
- `GET /api/health` - Service health check with feature flags

### Data Flow

1. User submits topic → `POST /api/debate/start` → HostAgent researches
2. Host generates research brief + focus options → frontend shows research results
3. User selects focus + intensity → `POST /api/debate/configure`
4. HostAgent creates debater configs → image service generates avatars/background
5. Stage pipeline executes: Opening → Free Debate → Closing → Summary
6. Report written to `data/reports/{timestamp}-{sanitized_topic}.md`
7. User can ask follow-up questions via `POST /api/debate/followup`

### Key Design Patterns

- **Stage Pipeline Pattern**: Debate stages are registered in `StageRegistry` and executed sequentially
- **Provider Pattern**: `LLMProvider` and `SearchProvider` abstractions allow swapping implementations
- **Agent Pattern**: Host and Debater agents encapsulate role-specific prompting
- **Context Management**: Rolling summaries prevent context overflow in long debates
- **Streaming Architecture**: SSE events stream tokens for real-time UI updates
- **Dependency Injection**: FastAPI dependencies provide singletons (session_store, report_writer, etc.)
