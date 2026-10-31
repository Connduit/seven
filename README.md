# AI Influencer Studio

Phase 1 foundation for managing fictional AI personalities. React + TypeScript + Vite frontend, FastAPI + SQLAlchemy + SQLite backend, and one shared OpenAI-compatible llama.cpp server.

## Run locally

Requires Python 3.11+ and Node.js 22+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock.txt
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the Vite address printed in your terminal. Vite proxies `/api` to the backend. API documentation is at port 8000 under `/docs`.

Start your existing llama.cpp server separately with its chat API at `http://127.0.0.1:8080/v1`. Backend settings can be supplied as environment variables before starting uvicorn:

- `LLM_BASE_URL`: OpenAI-compatible base URL (default above).
- `LLM_MODEL`: model identifier served by llama.cpp (default `local`; set to the server's model alias if required).
- `LLM_API_KEY`: optional server key (default `local`).
- `DATABASE_URL`: defaults to `sqlite:///./studio.db`, relative to the backend working directory. Keep using that working directory to reuse data.

The cloud environment cannot reach a llama.cpp server on your own computer through localhost. Run both on the same machine, or provide a reachable secured inference endpoint. Database-backed management works without inference; generation returns a useful 503 error when inference is unavailable. Inference HTTP requests use direct networking for the local server and do not use proxy-injected credentials.

## Available now

Create and edit characters, configure personality/interests/goals, organize active/paused/archived status, chat with independent persisted histories, and generate persisted unpublished post drafts. Failed generation does not save partial conversations. The last 20 chat entries are sent as context. SQLite stores data across backend restarts.

Status is organizational only. Autonomous loops, memory retrieval, social integrations, publishing, financial operations, authentication, and multi-user access are not implemented. Run this initial version as a trusted local workspace. No real social posts or financial actions are executed. Styling currently uses custom CSS; Tailwind/shadcn integration and scheduling are deferred.

## Validate

```bash
cd backend
../.venv/bin/python -m pytest -q
cd ../frontend
npm run build
```

API tests use isolated in-memory databases and a deterministic inference stub; they do not claim to validate a live LLM. See [PROJECT_SPEC.md](PROJECT_SPEC.md) for the full roadmap.

## Influencer profiles

Click a character card to open Overview: personality, interests, primary goal, status, studio message/draft counts, and last activity. Add or remove saved HTTPS profile links for Instagram, TikTok, YouTube, X, Bluesky, and Reddit. These are public links, not authenticated account connections. Audience analytics remain unavailable until platform integrations exist. The social page table is created automatically on backend startup; existing characters and histories are preserved.
