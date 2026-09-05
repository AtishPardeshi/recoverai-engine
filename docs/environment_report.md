# Environment Inspection Report (Phase 0)

**Project:** RecoverAI — Autonomous Revenue Recovery Platform  
**Date:** September 5, 2026  
**Host OS:** macOS (Darwin arm64/x86_64)  
**Workspace:** `recoverai` (Project Root)

---

## 1. Runtime & Tooling Summary

| Component | Detected Version | Status / Notes |
| :--- | :--- | :--- |
| **Python** | 3.14.5 | Available. Core backend runtime. |
| **Pip** | 26.1.1 | Available. |
| **Node.js** | v24.12.0 | Available. Modern React/Vite frontend runtime. |
| **npm** | 11.6.2 | Available. Package manager for frontend. |
| **Git** | 2.50.1 | Available. |
| **Docker** | Not present on host | Local running supported out-of-the-box using SQLite (Postgres-compatible SQLAlchemy models) with full Dockerfile/docker-compose provided for deployment. |
| **LLM Keys** | None set in env | Implemented dual-mode agent: External LLM provider abstraction (Gemini/OpenAI) + Deterministic Calibrated AI Decision Engine fallback. |

---

## 2. Workspace Assessment

- **Initial State:** Empty project workspace.
- **Isolation:** Standalone virtual environment (`.venv`) created for Python dependencies.
- **Frontend Strategy:** React 18 + TypeScript + Vite + Tailwind/Lucide-React + Recharts for a high-performance, responsive, rich fintech UX.
- **Backend Strategy:** FastAPI + Pydantic v2 + SQLAlchemy 2.0 (dialect-agnostic, SQLite for zero-config local demo & PostgreSQL production ready) + scikit-learn (`HistGradientBoostingClassifier`).

---

## 3. Key Dependencies Verified

- `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`
- `sqlalchemy`
- `scikit-learn`, `numpy`, `pandas`
- `pytest`, `httpx`
- `faker`

---

## 4. Phase 0 Outcome

- **Status:** **PASS**
- **Risks Identified & Mitigated:**
  1. *Docker not installed*: SQLite used for local frictionless execution with exact PostgreSQL DDL compatibility via SQLAlchemy.
  2. *LLM API key optional*: Zero-friction deterministic AI agent engine ensures 100% test and demo reliability without internet or API quotas.
