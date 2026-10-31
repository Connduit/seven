# AI Influencers (v0.2): local LLM + Instagram

## 1. Local LLM
Any OpenAI-compatible server works. For llama.cpp:
```bash
llama-server -m /path/to/model.gguf --port 8080 -c 8192
```
Env vars (defaults shown): `LLM_URL=http://localhost:8080/v1`, `LLM_MODEL=local` (set the real name for Ollama/LM Studio), `LLM_TIMEOUT=300`.
No model running? `LLM_MOCK=1` returns canned responses for UI testing.

## 2. Backend (port 8100)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
LLM_URL=http://localhost:8080/v1 uvicorn app.main:app --reload --port 8100
```

## 3. Frontend (http://localhost:5173)
```bash
cd frontend && npm install && npm run dev
```
To change the backend port, edit `frontend/vite.config.js` and the `--port` flag.

## 4. Instagram
Needs an Instagram **professional** (Business/Creator) account, plus a Meta developer app with the Instagram content-publishing permission (see Meta's "Content Publishing" docs for Business Login for Instagram). Paste the account ID and access token into the persona's Instagram section.
- Posts require an image at a **publicly reachable URL** (Meta downloads it). Paste it when approving.
- Limit: 100 API-published posts per 24h per account.
- Captions get an "AI-generated influencer" footer automatically. Also turn on Instagram's AI label in the app where offered.
- Without credentials, approving just logs a dry run.
- Overrides: `IG_HOST`, `IG_API_VERSION` (default v25.0).

## Not built yet
Image generation, scheduler, automatic Instagram posting (needs images), replies/comments, metrics.
