# How to Execute and Run the COBOL Modernizer

Step-by-step guide to run the platform locally for review, demo, or development.

| Component | Folder | URL |
|---|---|---|
| Backend (FastAPI) | `cobol-modernization-service/` | http://127.0.0.1:8010 |
| Frontend (Next.js) | `cobol-modernization-dashboard/` | http://localhost:3000 |
| API docs (Swagger) | — | http://127.0.0.1:8010/docs |

---

## Before you start — prerequisites

Install these on your machine:

| Tool | Version | Required for |
|---|---|---|
| Python | 3.11+ | Backend |
| Node.js | 20+ | Frontend |
| npm | (bundled with Node) | Frontend |
| OpenJDK | 21 | Java compile step in the pipeline |
| GnuCOBOL (`cobc`) | 3.1+ | Optional — behavioral diff only |
| LLM API key | — | Parse-only works without it; **analyze + convert require a key** |

Supported LLM providers (set one key in `.env`):

- Anthropic (`ANTHROPIC_API_KEY`)
- OpenAI / Azure OpenAI (`OPENAI_API_KEY` + optional `OPENAI_ENDPOINT`)
- OpenRouter (`OPENROUTER_API_KEY`)
- Google (`GOOGLE_API_KEY`)

---

## Step 1 — Clone and open the repository

```bash
git clone https://github.com/NourSAHLI17/version-solide-du-code-acc-l-rateur-de-conversion-COBOL-.git
cd version-solide-du-code-acc-l-rateur-de-conversion-COBOL-
```

On Windows, you can use the same repo path you already have; all commands below work from the **repository root** (`cobol/`).

---

## Step 2 — Backend setup

### 2.1 Create a Python virtual environment

**Windows (PowerShell):**

```powershell
cd cobol-modernization-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
cd cobol-modernization-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.2 Configure environment variables

Copy the example file and edit it:

```powershell
copy .env.example .env
```

Open `cobol-modernization-service/.env` and set at minimum:

```env
HOST=0.0.0.0
PORT=8010

LLM_PROVIDER=auto
ANTHROPIC_API_KEY=your_key_here
# — or OPENAI_API_KEY, OPENROUTER_API_KEY, GOOGLE_API_KEY

PARSER_BACKEND=hybrid
ANALYSIS_ENGINE=llm
JAVA_PROJECT_PROFILE=plain_java
```

> **Important:** The canonical port for this project is **8010**. Do not use 8000 or 8002 (legacy dev ports).

Never commit a real `.env` file — it is gitignored.

### 2.3 Start the backend

**Option A — from repository root (Windows):**

```bat
start_backend.bat
```

**Option B — manual (all platforms):**

```bash
cd cobol-modernization-service
# activate .venv first (see Step 2.1)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### 2.4 Verify the backend is running

Open in a browser or run:

```bash
curl http://127.0.0.1:8010/api/status
```

Expected: JSON response with service status. If you configured an LLM key, `llm_configured` should be `true`.

Optional — check compile toolchains (for behavioral diff):

```bash
curl "http://127.0.0.1:8010/api/testing/toolchain-status?force_refresh=true"
```

Swagger UI (interactive API explorer): http://127.0.0.1:8010/docs

---

## Step 3 — Frontend setup

Open a **second terminal** (keep the backend running).

### 3.1 Install dependencies

```bash
cd cobol-modernization-dashboard
npm install
```

### 3.2 Configure the API URL

Copy the example file:

```powershell
copy .env.local.example .env.local
```

Or create `cobol-modernization-dashboard/.env.local` manually:

```env
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010/api
```

### 3.3 Start the frontend

**Option A — from repository root (Windows):**

```bat
start_frontend.bat
```

**Option B — manual:**

```bash
cd cobol-modernization-dashboard
npm run dev
```

### 3.4 Verify the frontend is running

Open http://localhost:3000 — you should see the dashboard home page.

---

## Step 4 — Run your first pipeline (recommended)

1. Ensure backend (**8010**) and frontend (**3000**) are both running.
2. Open http://localhost:3000
3. Go to **Single File** (or `/convert/single`).
4. Paste or upload a COBOL program from the sample test case:
   - `acme-bank-v3/src/LOANEVAL.cbl` (main loan evaluation program)
   - or `acme-bank-v3/src/RISKSCOR.cbl` (smaller program, faster run)
5. Run the pipeline stages: **Parse → Analyze → Convert**.
6. Review JSON artifacts and generated Java in the UI.

### Sample programs (`acme-bank-v3/`)

| File | Role |
|---|---|
| `LOANEVAL.cbl` | Main controller — uses constrained conversion mode |
| `RISKSCOR.cbl` | Risk scoring |
| `CALCFEE.cbl` | Fee calculation |
| `CHKAML.cbl` | AML check |
| `RECOVRY.cbl` | Recovery processing |
| `RPTMONTH.cbl` | Monthly reporting |

For a **full project upload** (ZIP with multiple COBOL files + copybooks), use the **Project Upload** page.

---

## Step 5 — Run backend tests (optional)

From `cobol-modernization-service/` with `.venv` activated:

```bash
python -m pytest -q
```

Focused integration tests:

```bash
python -m pytest tests/test_usecase3_pipeline.py -v
```

---

## Quick reference — URLs

```text
Dashboard:     http://localhost:3000
Backend API:   http://127.0.0.1:8010/api
Swagger UI:    http://127.0.0.1:8010/docs
Health check:  http://127.0.0.1:8010/api/status
```

Main dashboard pages:

| Page | Path |
|---|---|
| Home / Cockpit | `/` or `/cockpit` |
| Single file pipeline | `/convert/single` |
| Project upload | `/convert/project` |
| Parser (debug) | `/parser` |
| Analysis (debug) | `/analysis` |
| Conversion | `/conversion` |
| Testing | `/testing/legacy` |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Frontend shows network errors | Backend must be on port **8010**. Check `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010/api` in `.env.local`. Restart `npm run dev` after changing it. |
| Analyze / Convert fails | Set at least one LLM API key in `cobol-modernization-service/.env`. Verify with `curl http://127.0.0.1:8010/api/status`. |
| `llm_configured: false` | Key missing or wrong variable name. Match `LLM_PROVIDER` to the key you set. |
| PowerShell blocks venv activation | Run: `Set-ExecutionPolicy -Scope Process Bypass` then activate again. |
| `pip` / `python` not found | Use `python3` and `pip3` on macOS/Linux, or install Python 3.11+ on Windows. |
| Behavioral diff unavailable | Install GnuCOBOL and JDK 21; ensure `cobc` and `javac` are on your PATH. Check `/api/testing/toolchain-status`. |
| Port 8010 already in use | Stop the other process or run: `python -m uvicorn app.main:app --port 8011 --reload` and update `.env.local` to match. |

---

## What to read next

| Document | Purpose |
|---|---|
| `README.md` | Project overview and architecture summary |
| `docs/architecture/ARCHITECTURE_README.md` | Full system architecture (EY review) |
| `RUN_GUIDE.md` | Compact operator reference (ports, curl commands) |
| `docs/architecture/DEVELOPER_GUIDE.md` | Developer deep-dive |

---

## Minimum command checklist

```text
[ ] Python 3.11+ and Node 20+ installed
[ ] cd cobol-modernization-service → venv → pip install -r requirements.txt
[ ] Copy .env.example → .env → set PORT=8010 + LLM key
[ ] Start backend on port 8010
[ ] curl http://127.0.0.1:8010/api/status → OK
[ ] cd cobol-modernization-dashboard → npm install
[ ] Copy .env.local.example → .env.local
[ ] npm run dev → open http://localhost:3000
[ ] Upload acme-bank-v3/src/LOANEVAL.cbl and run pipeline
```
