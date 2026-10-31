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

Click a character card to open Overview: personality, interests, primary goal, status, studio message/draft counts, and last activity. Add or remove saved HTTPS profile links for Instagram, TikTok, YouTube, X, Bluesky, Reddit, and Snapchat. These are public links, not authenticated account connections. Audience analytics remain unavailable until platform integrations exist. The social page table is created automatically on backend startup; existing characters and histories are preserved.

## Instagram account authorization (initial integration)

Instagram is the first OAuth adapter; other platforms remain public profile links. This uses Instagram API with Instagram Login for professional Business/Creator accounts. No social passwords are collected. Tokens are encrypted with Fernet before SQLite persistence and are never returned to the browser. An expiring, single-use state and HttpOnly browser cookie bind each authorization to its initiating browser and influencer.

1. Create a Meta developer app and configure **Instagram API with Instagram Login**. Follow Meta's current [Business Login documentation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login/). Request `instagram_business_basic` and `instagram_business_content_publish`. Development mode generally requires assigned test/app roles; access for other users requires Meta's applicable review and permissions.
2. Serve the frontend and `/api` through **one HTTPS origin** (including for local OAuth testing), and register the exact callback `https://YOUR-HOST/api/integrations/instagram/callback` in the app configuration. The OAuth cookie requires HTTPS. Configure your reverse proxy to route `/api` to FastAPI and all other paths to the frontend. Keep the local development servers private; Vite's default development host rules must explicitly allow your chosen host if proxying to Vite. Do not disable host validation globally.
3. Copy `backend/.env.example` to `backend/.env`. Fill `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI`, and `STUDIO_FRONTEND_URL`. These values must match your Meta app and HTTPS origin. Generate keys locally:

   ```bash
   .venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   .venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
   ```

   Use the first as `TOKEN_ENCRYPTION_KEY`, the second as `STUDIO_ADMIN_KEY`. Keep them private; do not paste them in chat, commit them, or reuse your Instagram password. Back up the encryption key separately: losing it makes saved tokens unusable. Key rotation and automatic token refresh are not implemented; reconnect expired accounts. `.env` is ignored by Git.
4. Install the updated `backend/requirements.lock.txt`, then from `backend` run `../.venv/bin/uvicorn app.main:app --env-file .env --port 8000 --no-access-log`. Configure your HTTPS proxy to omit OAuth callback query strings from access logs too (authorization codes and state are sensitive). Use TLS verification normally. Required outbound hosts are `www.instagram.com`, `api.instagram.com`, and `graph.instagram.com`.
5. Open an influencer's Overview, enter your **studio administrator key**, and click **Connect Instagram**. Authorize on Instagram, then reopen the influencer and unlock settings again. The administrator key lives only in browser memory; refreshing clears it. Instagram authorization returns a token expiry date; reconnect as needed. One Instagram account can belong to only one influencer. Reconnecting resets the publishing policy to Disabled.
6. Set Disabled or Require creator approval and a future daily post limit. **No publishing API, scheduler, automatic refresh, or autonomous posting is implemented.** These settings are stored configuration, not a working approval queue or publishing control. Disconnect removes the token locally; revoke app access in Instagram settings as well if desired. Deleting a linked influencer requires the studio key and clears its connection credentials.

This remains a trusted single-user local application: the existing character/chat/profile-link APIs do not have full user authentication. The administrator key protects credential-management endpoints, not the entire workspace. Before making it publicly accessible, implement full login/authorization, HTTPS deployment, backups, token refresh, audit logging, and tested publishing/approval enforcement. Do not expose the development server to the Internet just to complete OAuth; use a restricted HTTPS deployment.

OAuth protocol tests use mocked Meta responses; a real account connection requires your app credentials and Meta configuration. Current provider documentation could not be fetched in the cloud due to its network allowlist, so verify your app's current setup requirements in Meta's linked documentation before live use.

## Accounts & credential vault

The **Accounts & vault** navigation item manages saved credentials for Gmail, social sites, and other services, alongside a central list of authorized Instagram accounts. Configure `STUDIO_ADMIN_KEY` (a random 32+ character key) and `TOKEN_ENCRYPTION_KEY` as described above; Meta credentials are not required to use the password vault. Reload dependencies after updating.

Unlock using the studio key, add a service and account label, enter the username/email and password, and optionally assign an influencer. Both username and password are encrypted before storage; labels, service names, website links, and assignment IDs are metadata stored without encryption. List APIs do not return usernames or passwords. Reveal explicitly displays credentials for 30 seconds; the vault clears its UI and in-memory administrator key when manually locked or after 5 minutes of inactivity. Switching browser tabs does not lock the vault. Editing permits password replacement; leaving the new password blank preserves the existing password. Deleting a saved entry removes it from the current database, not from the provider or old backups. Deleting an assigned influencer requires the administrator key and preserves saved credentials as unassigned workspace accounts.

These are **saved credentials, not active connections**. The AI cannot retrieve them and they are never added to model prompts or used to automate logins. Gmail/Google OAuth is not implemented. Use official platform OAuth APIs for future email/social automation, including Gmail; storing a Google password does not bypass 2FA or authorize Gmail API access. Existing authorized Instagram connections can be reviewed, disconnected, and assigned a future approval policy from this page.

Use this initial vault only in a trusted single-user environment behind HTTPS or on local loopback. It has administrator-key authentication and encryption at rest, not full user accounts, hardware-backed key storage, enterprise auditing, or security review. The encryption key must remain separate from database backups and stable across restarts. A compromised server or browser can still expose unlocked credentials. For valuable production credentials, prefer an established password manager until this application has undergone authentication hardening and independent security review. Do not send passwords or encryption keys in chat.

## Character voice

Creator chat and caption drafts share character instructions in `backend/app/prompts.py`. Personas speak in first person with their configured traits and interests, avoiding routine assistant/AI disclaimers. They answer direct questions about being fictional truthfully and distinguish imagined scenes or proposed captions from real events and completed actions. Draft generation does not publish content or establish that a fictional trip happened. Existing profile transparency labels remain visible. Restart the backend to apply changes; no model retraining or database migration is needed.

Tests verify the instructions and isolated character context sent to the inference API using a mock HTTP transport. Actual writing style and adherence depend on your model; test your local llama.cpp server with ordinary conversation, a beach-caption request, and direct questions such as “Are you a real human?” and “Did that trip actually happen?”. Structured storyline memory and a post approval queue remain future work.

Snapchat supports saved public profile links (for example `https://www.snapchat.com/add/yourusername`) and encrypted vault credentials. Snapchat OAuth, analytics, and publishing are not implemented.
