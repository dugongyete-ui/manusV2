# AI Manus - AI Agent Platform

## Overview
AI Manus is an AI agent platform cloned from GitHub. It provides an AI assistant that can perform tasks using tools like browser, file management, shell commands, and search. Powered by custom LLM API (Claude via Perplexity provider).

## Architecture
- **Frontend**: Vue 3 + Vite + TypeScript (port 5000)
- **Backend**: FastAPI + Python (port 8000)
- **Sandbox**: FastAPI service for shell/file operations (port 8080)
- **Database**: MongoDB (port 27017) + Redis (port 6379)
- **LLM**: Custom API gateway with Perplexity provider, model claude37sonnetthinking

## Project Structure
```
/backend          - FastAPI backend (auth, agent, sessions)
/frontend         - Vue 3 frontend (chat UI, login, file viewer)
/sandbox          - Sandbox service (shell, file operations)
/docs             - Documentation
/start.sh         - Main startup script (all services)
/install.sh       - Auto-install all dependencies
```

## LLM Configuration
- Type: `custom` (custom API adapter)
- Provider: `Perplexity`
- Model: `claude37sonnetthinking`
- API Base: `https://api-dzeck--lizqz5hk.replit.app` (env: API_BASE)
- Supports both OpenAI-compatible (`openai` type) and custom API format (`custom` type)
- Custom adapter: `/backend/app/infrastructure/external/llm/custom_llm.py`
- API response format: `{"data": "...", "status": "success"}` - content extracted from `data` field

## Auth Configuration
- Auth mode: `local` (configured via AUTH_PROVIDER env var)
- Login: admin@manus.ai / admin123
- Supports: password (registration), local (preconfigured), none (no auth)

## API Endpoints
- `GET /api/v1/health` - System health check (LLM config, API key status)
- `GET /api/v1/health/llm` - Live LLM API connection test (tests actual API call)
- `POST /api/v1/auth/login` - User authentication
- `PUT /api/v1/sessions` - Create new chat session
- `POST /api/v1/sessions/{id}/chat` - Chat with AI (SSE streaming)

## Environment Variables
- `API_KEY` - LLM API key (secret)
- `API_BASE` - LLM API base URL
- `LLM_TYPE` - LLM type: openai or custom
- `LLM_PROVIDER` - LLM provider name (e.g., Perplexity)
- `MODEL_NAME` - Model name (e.g., claude37sonnetthinking)
- `AUTH_PROVIDER` - Auth mode: local, password, none
- `LOCAL_AUTH_EMAIL` - Local auth email
- `LOCAL_AUTH_PASSWORD` - Local auth password
- `MONGODB_URI` - MongoDB connection string
- `REDIS_HOST` - Redis host
- `SANDBOX_ADDRESS` - Sandbox service URL
- `JWT_SECRET_KEY` - JWT signing key

## Recent Changes
- 2026-02-20: Chat flow fully working end-to-end
  - Fixed critical bug: Custom LLM API returns `{"data": "...", "status": "success"}` wrapper - now correctly extracts `data` field
  - Fixed Plan validation: `message` field can be None, handle gracefully
  - Fixed MessageEvent: handle None content without crashing
  - Made browser optional: system works without Chrome/Playwright CDP
  - Planner no longer sends tools when tool_choice is "none"
  - Added summarizer fallback: when plan has 0 steps and no message, triggers summarization
  - Fixed status enum mapping: LLM returns "success" mapped to "completed"
  - LLMJsonParser now uses correct LLM type (custom vs openai) based on config
  - Sandbox ensure_sandbox handles local mode (no supervisor services)
  - Improved error handling throughout agent stack
- 2026-02-20: API improvements and health monitoring
  - Updated API_BASE to https://api-dzeck--lizqz5hk.replit.app
  - Added health check endpoints (/api/v1/health, /api/v1/health/llm)
  - Improved Custom LLM adapter: retry with jitter, better timeouts, error handling
- 2026-02-20: Switched from DeepSeek to Custom API
  - Created custom LLM adapter for non-OpenAI API format
  - Configured Perplexity provider with claude37sonnetthinking model
- 2026-02-20: Initial setup on Replit
  - Created install.sh for auto dependency installation
  - Configured local auth (admin@manus.ai / admin123)
  - All services running: MongoDB, Redis, Sandbox, Backend, Frontend

## Key Design Decisions
- Browser tools are optional (no Chrome/CDP on Replit)
- Sandbox runs locally on port 8080 (not Docker containers)
- Status normalization: maps various LLM status strings (success, done, error) to enum values
- Custom LLM adapter handles non-OpenAI API response formats

## User Preferences
- Language: Indonesian (Bahasa Indonesia)
- Project cloned from GitHub, needs development assistance
