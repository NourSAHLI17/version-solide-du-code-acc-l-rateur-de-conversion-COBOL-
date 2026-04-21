# COBOL Modernization Project Run Guide

This guide explains how to run the full project locally:

- backend: `cobol-modernization-service`
- frontend: `cobol-modernization-dashboard`

It includes:

- dependency installation
- `.env` creation
- backend startup
- frontend startup
- test commands
- common URLs

## Prerequisites

Install these first:

- Python 3.11+ or 3.12
- Node.js 20+
- npm
- PowerShell on Windows

Recommended folder layout:

```text
D:\cobol\
  cobol-modernization-service\
  cobol-modernization-dashboard\
```

## 1. Backend Setup

Open PowerShell and go to the backend:

```powershell
cd D:\cobol\cobol-modernization-service
```

### Create a virtual environment

```powershell
python -m venv .venv
```

### Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

### Install backend dependencies

```powershell
pip install -r requirements.txt
```

### Create backend `.env`

Create a file named `.env` inside:

```text
D:\cobol\cobol-modernization-service\.env
```

Example:

```env
HOST=0.0.0.0
PORT=8000

# Choose one provider: openai | google | openrouter | auto
LLM_PROVIDER=openai

# OpenAI
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini

# Google Gemini
GOOGLE_API_KEY=your_google_api_key_here

# OpenRouter
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=qwen/qwen3-coder:free

# Parser backend
PARSER_BACKEND=heuristic
```

Notes:

- Only one provider needs to be active at a time through `LLM_PROVIDER`.
- For local development, `PARSER_BACKEND=heuristic` is the stable option.
- Do not commit real API keys to git.

### Run backend tests

```powershell
python -m unittest discover -s tests
```

### Run backend lint

```powershell
ruff check .
```

### Start the backend API

Option 1:

```powershell
python main.py
```

Option 2:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend URLs:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/api/status
http://127.0.0.1:8000/api/parse
http://127.0.0.1:8000/api/analyze
http://127.0.0.1:8000/api/convert
http://127.0.0.1:8000/api/validate
```

## 2. Frontend Setup

Open a second PowerShell window and go to the frontend:

```powershell
cd D:\cobol\cobol-modernization-dashboard
```

### Install frontend dependencies

```powershell
npm install
```

### Create frontend `.env.local`

Create this file:

```text
D:\cobol\cobol-modernization-dashboard\.env.local
```

Example:

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000/api
```

Notes:

- This is optional for local use because the frontend already defaults to `http://localhost:8000/api`.
- Use it if your backend runs on another host or port.

### Run frontend lint

```powershell
npm run lint
```

If `npm run lint` has shell issues on Windows, use:

```powershell
.\node_modules\.bin\eslint.cmd .
```

### Start the frontend

```powershell
npm run dev
```

Frontend URL:

```text
http://localhost:3000
```

Main pages:

```text
http://localhost:3000/
http://localhost:3000/parser
http://localhost:3000/analysis
http://localhost:3000/conversion
http://localhost:3000/validation
http://localhost:3000/cockpit
```

### Production build check

```powershell
npm run build
```

If Windows blocks the standard script, use:

```powershell
.\node_modules\.bin\next.cmd build
```

## 3. Recommended Run Order

Start the backend first:

```powershell
cd D:\cobol\cobol-modernization-service
.\.venv\Scripts\Activate.ps1
python main.py
```

Then start the frontend:

```powershell
cd D:\cobol\cobol-modernization-dashboard
npm run dev
```

Then open:

```text
http://localhost:3000/cockpit
```

## 4. Quick Health Checks

### Backend health

```powershell
curl http://localhost:8000/api/status
```

Expected response includes fields like:

- `api_healthy`
- `llm_configured`
- `conversion_available`
- `llm_model`

### Backend import check

```powershell
python -c "from app.main import app; print(app.title)"
```

### Frontend API target check

The frontend is wired to:

- `NEXT_PUBLIC_API_BASE` if set
- otherwise `http://localhost:8000/api`

## 5. Troubleshooting

### Backend `.env` not loading

Check that:

- the file is named exactly `.env`
- it is inside `D:\cobol\cobol-modernization-service`
- there are no extra quotes around keys unless intended

### LLM configured but conversion fails

Possible causes:

- invalid API key
- quota exceeded
- provider rate limit
- network restrictions

Check:

```powershell
python -c "from app.agents.conversion_agent import ConversionAgent; print(ConversionAgent().get_runtime_status())"
```

### Frontend cannot reach backend

Check:

- backend is running on port `8000`
- `NEXT_PUBLIC_API_BASE` points to the correct backend
- browser can open `http://localhost:8000/api/status`

### PowerShell execution policy blocks `.venv`

Use:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### Next.js build fails with Windows process restrictions

Try:

```powershell
.\node_modules\.bin\next.cmd build
```

## 6. Full Command Summary

### Backend

```powershell
cd D:\cobol\cobol-modernization-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests
ruff check .
python main.py
```

### Frontend

```powershell
cd D:\cobol\cobol-modernization-dashboard
npm install
npm run lint
npm run dev
```
