# COBOL Modernization Project — Run Guide

How to run the platform locally for review or development.

| Component | Folder | Default URL |
|---|---|---|
| Backend | `cobol-modernization-service/` | `http://127.0.0.1:8010` |
| Frontend | `cobol-modernization-dashboard/` | `http://localhost:3000` |
| Architecture docs | `docs/architecture/` | — |

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm
- OpenJDK 21 (for Java compile / behavioral diff)
- GnuCOBOL 3.1+ (optional; required for behavioral diff)
- At least one LLM provider API key

---

## Quick start (Windows)

From the repository root:

```bat
start_backend.bat
start_frontend.bat
```

- Backend: `http://127.0.0.1:8010` — Swagger UI at `/docs`
- Frontend: `http://localhost:3000`

---

## 1. Backend setup

```powershell
cd cobol-modernization-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `cobol-modernization-service/.env` (copy from `.env.example` if present):

```env
HOST=0.0.0.0
PORT=8010

LLM_PROVIDER=auto
ANTHROPIC_API_KEY=your_key_here
# or OPENAI_API_KEY, OPENROUTER_API_KEY, GOOGLE_API_KEY

PARSER_BACKEND=hybrid
ANALYSIS_ENGINE=llm
JAVA_PROJECT_PROFILE=plain_java
```

Do not commit real API keys.

### Start the backend (port 8010)

**Recommended:**

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

Or from repo root: `start_backend.bat`.

### Verify backend health

```powershell
curl.exe -s http://127.0.0.1:8010/api/status
curl.exe -s "http://127.0.0.1:8010/api/testing/toolchain-status?force_refresh=true"
```

### Run backend tests

```powershell
python -m pytest -q
```

### Backend API URLs (8010)

```text
http://127.0.0.1:8010/docs
http://127.0.0.1:8010/api/status
http://127.0.0.1:8010/api/parse
http://127.0.0.1:8010/api/analyze
http://127.0.0.1:8010/api/convert
http://127.0.0.1:8010/api/testing/behavioral-diff
```

> **Note:** Older dev scripts under `cobol-modernization-service/scripts/` (e.g. `start-api-8002.ps1`) and ports **8000** / **8002** are obsolete. The active handoff port is **8010**, matching `start_backend.bat` and the dashboard `.env.local`.

---

## 2. Frontend setup

```powershell
cd cobol-modernization-dashboard
npm install
```

Create `cobol-modernization-dashboard/.env.local`:

```env
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010/api
```

### Start the frontend

```powershell
npm run dev
```

Open `http://localhost:3000`.

Main pages: `/`, `/parser`, `/analysis`, `/conversion`, `/validation`, `/cockpit`.

---

## 3. Recommended run order

1. Start backend on port **8010**
2. Start frontend on port **3000**
3. Open `http://localhost:3000/cockpit` or Single File page
4. Upload or paste COBOL from `acme-bank-v3/src/` for a full pipeline test

---

## 4. Troubleshooting

| Problem | Check |
|---|---|
| Frontend cannot reach backend | Backend running on **8010**; `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010/api` |
| LLM not configured | `curl http://127.0.0.1:8010/api/status` — `llm_configured` should be true |
| Behavioral diff unavailable | `toolchain-status` — `cobc` and `javac` must be on PATH |
| PowerShell blocks venv activation | `Set-ExecutionPolicy -Scope Process Bypass` |

---

## 5. Full command summary

### Backend

```powershell
cd cobol-modernization-service
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### Frontend

```powershell
cd cobol-modernization-dashboard
npm run dev
```
