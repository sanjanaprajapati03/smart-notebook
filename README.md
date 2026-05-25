# Second Brain

An AI-powered personal knowledge management system that stores notes, automatically chunks and embeds them into a vector-graph database (Neo4j), and uses Google Gemini to discover hidden relationships across your notes.

**Architecture:** Two-process Python system — FastAPI backend + Streamlit frontend — orchestrated via Docker Compose.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Data Flow](#data-flow)
- [Database Entities](#database-entities)
- [API Reference](#api-reference)
- [How to Access Data](#how-to-access-data)
- [Configuration](#configuration)
- [Setup & Running](#setup--running)
- [Key Implementation Details](#key-implementation-details)

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Runtime** | Python ≥3.14 | Application language |
| **Backend framework** | FastAPI 0.136+ | REST API server |
| **Frontend framework** | Streamlit 1.35+ | Web UI |
| **Package manager** | `uv` | Python venv & deps |
| **Auth database** | PostgreSQL 16 | User accounts (via `asyncpg`) |
| **Graph database** | Neo4j 5.18 | Notes, chunks, embeddings, relationships (via `neo4j` driver) |
| **Embeddings** | Google Gemini `text-embedding-004` (optional) | 1536-dim vector embeddings |
| **Chat model** | Google Gemini `gemini-2.5-flash` (optional) | Relationship discovery |
| **Auth** | `passlib[bcrypt]` + `python-jose[cryptography]` | Password hashing & JWT |
| **Containers** | Docker Compose | PostgreSQL + Neo4j locally |

---

## Project Structure

```
second-brain/
├── .env                          # Environment variables (git-ignored)
├── .gitignore
├── .python-version               # Python 3.14
├── Makefile                      # dev commands: db, api, ui, dev, down
├── README.md                     # This file
├── docker-compose.yml            # Neo4j 5.18 + PostgreSQL 16 containers
├── pyproject.toml                # Project metadata & dependencies (uv)
├── uv.lock                       # Locked dependency versions
│
├── src/                          # ═══════ BACKEND (FastAPI) ═══════
│   ├── main.py                   # Entry point: FastAPI app, lifespan (DB init, pool creation)
│   ├── state.py                  # Global module state: db_driver (Neo4j), pg_pool (PostgreSQL)
│   ├── utils.py                  # chunk_text() splitter, get_mock_embedding() deterministic fallback
│   ├── dependencies.py           # get_current_user() — JWT decode + DB lookup
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # All env vars: Neo4j URI/cred, PG DSN, Gemini keys, JWT settings
│   │   └── security.py           # bcrypt hash/verify, JWT create, OAuth2 scheme
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py             # GET /health — simple liveness check
│   │   ├── auth.py               # Register, login, me — Pydantic models + route handlers
│   │   └── notes.py              # CRUD + ingestion + SSE discovery — core business logic
│   │
│   └── services/
│       ├── __init__.py
│       └── users.py              # PostgreSQL queries: fetch/create users
│
└── ui/                           # ═══════ FRONTEND (Streamlit) ═══════
    ├── __init__.py
    ├── app.py                    # Entry point: page routing, sidebar nav, auth gating
    ├── api.py                    # HTTP helper: api_request(), health check, error formatting
    ├── session.py                # Auth session: cache + st.session_state with TTL expiry
    ├── query_params.py           # URL query param abstraction (?page=, ?sid=)
    │
    └── views/
        ├── __init__.py
        ├── login.py              # Login form → POST /v1/auth/login
        ├── register.py           # Registration form → POST /v1/auth/register
        ├── notes.py              # Add note form + list notes with expanders
        └── discovery.py          # Select notes → SSE stream → display Gemini analysis
```

### File-by-file breakdown

| File | What it does |
|------|-------------|
| `src/main.py` | Creates the FastAPI app, starts an async lifespan that initializes PostgreSQL connection pool, Neo4j driver, creates the `users` table, Neo4j uniqueness constraints, and the vector index. Includes routers for `/v1/auth`, `/v1/notes`, and `/health`. |
| `src/state.py` | Two module-level globals: `db_driver` (Neo4j async driver) and `pg_pool` (asyncpg connection pool). Set during lifespan, read by all handlers. |
| `src/utils.py` | `chunk_text(text, chunk_size=500, overlap=100)` — splits text into overlapping 500-char slices. `get_mock_embedding(text)` — deterministic 1536-dim hash-based bag-of-words fallback when no Gemini key is present. |
| `src/dependencies.py` | FastAPI dependency `get_current_user` that decodes the JWT via `python-jose`, extracts `sub` (user_id), fetches the user from PostgreSQL, and returns the record dict. |
| `src/core/config.py` | Loads `.env`, exports all configuration constants: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `POSTGRES_DSN`, `GEMINI_API_KEY`, `GEMINI_CHAT_MODEL`, `GEMINI_EMBEDDING_MODEL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`. |
| `src/core/security.py` | `verify_password` / `get_password_hash` (bcrypt), `create_access_token` (JWT with HS256, sub=user_id, exp=now+TTL), `oauth2_scheme` (OAuth2PasswordBearer). Enforces 72-byte bcrypt limit. |
| `src/routes/health.py` | Single endpoint: `GET /health` → `{"status": "healthy"}`. |
| `src/routes/auth.py` | Three endpoints with Pydantic models: `POST /register` (creates user, returns JWT), `POST /login` (validates credentials, returns JWT), `GET /me` (returns current user profile). Passwords hashed, emails unique. |
| `src/routes/notes.py` | Core logic: `POST /notes` and `POST /notes/ingest` (creates a Note node, returns immediately, schedules background chunking+embedding). `GET /notes` (lists notes, paginated). `GET /notes/discover` (SSE streaming endpoint — fetches notes, aggregates them, sends to Gemini chat, streams tokens back). Also contains `process_and_index_note` background task (chunks text → embeds chunks → MERGE into Neo4j), `get_embeddings` (calls Gemini or fallback), cosine_similarity helper, and Gemini model fallback selection logic. |
| `src/services/users.py` | Three async functions: `get_user_by_email`, `get_user_by_id`, `create_user` — all raw SQL via `asyncpg` on the global `state.pg_pool`. |
| `ui/app.py` | Streamlit entry point. Sets page config, ensures a session ID (?sid=), hydrates auth from cache. Routes pages via ?page= param. Shows sidebar (Notes / Discover / Log out) when authenticated; hides sidebar and shows Login/Register when not. |
| `ui/api.py` | `api_request(method, path, token, **kwargs)` — wrapper around `requests.request` with Bearer token injection and base URL from session state. `check_api_health()` — calls GET /health. `format_api_error()` — extracts error detail from response JSON. `render_api_connection_panel()` — text input to change API URL + health indicator. |
| `ui/session.py` | In-memory `_SESSION_CACHE` dict keyed by session ID. `set_auth()` saves JWT + user + expiry to both `st.session_state` and `_SESSION_CACHE`. `hydrate_auth_from_store()` restores auth from `_SESSION_CACHE` on page reload. `clear_auth()` removes both. TTL = `ACCESS_TOKEN_EXPIRE_MINUTES`. |
| `ui/query_params.py` | Compatible wrapper around `st.query_params` / legacy `st.experimental_get_query_params`. `get_query_page()` / `set_query_page()` read/write `?page=` parameter. |
| `ui/views/login.py` | Renders email/password form, POSTs to `/v1/auth/login`, on success stores auth via `set_auth()` and navigates to "notes". |
| `ui/views/register.py` | Renders email/password form, POSTs to `/v1/auth/register`, on success stores auth and navigates to "notes". |
| `ui/views/notes.py` | Two modes (radio): "Add note" — title+content form → POST `/v1/notes`; "List notes" — slider for limit, button to refresh, cached expandable list from GET `/v1/notes`. |
| `ui/views/discovery.py` | Loads notes, multi-select to pick which notes to analyze, "Analyze notes" button → GET `/v1/notes/discover` (SSE) → streams and renders Gemini's analysis in a markdown block. |

---

## Data Flow

```
User (Streamlit in browser)
  │
  │ 1. Register / Login
  │    → POST /v1/auth/register or /v1/auth/login
  │    ← JWT access_token + user profile
  │
  │ 2. Write a note (title + content)
  │    → POST /v1/notes  (Authorization: Bearer <JWT>)
  │    Note is immediately MERGED into Neo4j
  │    ← { "status": "queued", "note_id": "..." }
  │
  │ 3. Background (FastAPI BackgroundTasks)
  │    process_and_index_note():
  │       a. Split note content into overlapping 500-char chunks
  │       b. Generate 1536-dim embedding for each chunk
  │          (Gemini API if key is set, else deterministic hash fallback)
  │       c. Delete old chunks for this note
  │       d. MERGE new Chunk nodes with text, index, embedding
  │       e. Re-link (Note)-[:HAS_CHUNK]->(Chunk)
  │
  │ 4. View notes list
  │    → GET /v1/notes?limit=50
  │    ← [{ id, content, created_at, updated_at }, ...]
  │
  │ 5. Discover relationships
  │    → GET /v1/notes/discover?note_ids=[...]  (SSE)
  │    Backend:
  │       a. Fetches user's selected notes from Neo4j
  │       b. Aggregates them into a formatted prompt
  │       c. Sends to Gemini chat model with streaming
  │       d. Yields SSE events: data: {"text":"..."}
  │    ← Streamed analysis rendered as Markdown
```

---

## Database Entities

### PostgreSQL — `users` table

Created on API startup in `src/main.py:23-33`.

```sql
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    BIGINT NOT NULL,       -- Unix timestamp (seconds)
    updated_at    BIGINT NOT NULL        -- Unix timestamp (seconds)
);
```

**Access:** Via `src/services/users.py` using raw SQL with `asyncpg` (no ORM).

| Function | SQL | Params |
|----------|-----|--------|
| `get_user_by_email(email)` | `SELECT ... WHERE email = $1 LIMIT 1` | email |
| `get_user_by_id(user_id)` | `SELECT ... WHERE id = $1 LIMIT 1` | user_id |
| `create_user(email, password_hash)` | `INSERT ... RETURNING id, email, ...` | uuid, email, hash, timestamps |

### Neo4j — Graph entities

Created dynamically during note ingestion.

**Node Labels:**

| Label | Properties | Created by |
|-------|-----------|------------|
| `User` | `{ id: string }` | MERGE on first note POST |
| `Note` | `{ id, user_id, content, created_at, updated_at }` | MERGE on POST /v1/notes |
| `Chunk` | `{ id, text, index, embedding: list<float>[1536] }` | Background task `process_and_index_note` |

**Relationships:**

| Relationship | Direction | Created by |
|-------------|-----------|------------|
| `(:User)-[:OWNS]->(:Note)` | User → Note | MERGE on POST /v1/notes |
| `(:Note)-[:HAS_CHUNK]->(:Chunk)` | Note → Chunk | MERGE in background task |

**Constraints (created on API startup):**

```cypher
CREATE CONSTRAINT unique_note_id IF NOT EXISTS FOR (n:Note) REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT unique_chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE
```

**Vector Index (created on API startup):**

```cypher
CREATE VECTOR INDEX note_chunks_vector_index IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS { indexConfig: { vector.dimensions: 1536, vector.similarity_function: 'cosine' } }
```

This index enables cosine-similarity searches across all chunk embeddings. It is **not currently queried directly in the code** but is ready for future use (e.g., semantic chunk search, relationship scoring).

### How to Access Database Records Directly

**PostgreSQL** (user accounts):

```bash
# Connect via psql
docker exec -it ai_engine_auth_db psql -U postgres -d second_brain

# List users
SELECT id, email, created_at FROM users;

# Check credentials (hash comparison via bcrypt check)
```

**Neo4j** (notes, chunks, embeddings):

```bash
# Connect via cypher-shell
docker exec -it ai_engine_graph cypher-shell -u neo4j -p password123

# List all users
MATCH (u:User) RETURN u.id;

# List all notes for a user
MATCH (u:User {id: '<user-id>'})-[:OWNS]->(n:Note) RETURN n.id, n.content, n.updated_at ORDER BY n.updated_at DESC;

# View chunks for a note
MATCH (n:Note {id: '<note-id>'})-[:HAS_CHUNK]->(c:Chunk) RETURN c.id, c.index, c.text ORDER BY c.index;

# Check embedding dimensions
MATCH (c:Chunk) RETURN c.id, size(c.embedding) AS dims LIMIT 1;

# Cosine similarity search (manual):
MATCH (c1:Chunk {id: '<chunk-id>'})
MATCH (c2:Chunk)
WHERE c1.id <> c2.id
RETURN c1.id, c2.id,
  gds.similarity.cosine(c1.embedding, c2.embedding) AS similarity
ORDER BY similarity DESC LIMIT 10;
```

Or browse Neo4j at http://localhost:7474 (browser UI).

---

## API Reference

All routes are prefixed under the FastAPI app. Authentication via `Authorization: Bearer <token>` header.

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Returns `{"status": "healthy"}` |

### Auth

| Method | Path | Auth | Request Body | Response |
|--------|------|------|-------------|----------|
| `POST` | `/v1/auth/register` | No | `{ "email": str, "password": str }` | `{ "access_token": str, "token_type": "bearer", "user": { id, email, created_at, updated_at } }` |
| `POST` | `/v1/auth/login` | No | `{ "email": str, "password": str }` | Same as register |
| `GET` | `/v1/auth/me` | JWT | — | `{ id, email, created_at, updated_at }` |

### Notes

| Method | Path | Auth | Query Params | Request Body | Response |
|--------|------|------|-------------|-------------|----------|
| `POST` | `/v1/notes` | JWT | — | `{ "content": str, "note_id"?: str, "timestamp"?: int }` | `{ "status": "queued", "note_id": str }` |
| `POST` | `/v1/notes/ingest` | JWT | — | Same as above | Same as above (alias) |
| `GET` | `/v1/notes` | JWT | `limit` (int, 1–200, default 50) | — | `[{ id, content, created_at, updated_at }, ...]` |
| `GET` | `/v1/notes/discover` | JWT | `limit` (int, default 10), `min_score` (float, default 0.78), `max_chunks` (int, default 200), `note_ids` (list[str]) | — | SSE stream: `data: {"text": "..."}\n\n` |

### Pydantic Models

| Model | Fields | Used in |
|-------|--------|---------|
| `UserRegisterRequest` | email, password | POST /v1/auth/register |
| `UserLoginRequest` | email, password | POST /v1/auth/login |
| `UserPublic` | id, email, created_at?, updated_at? | GET /v1/auth/me, nested in TokenResponse |
| `TokenResponse` | access_token, token_type="bearer", user: UserPublic | Auth responses |
| `NoteCreateRequest` | content, note_id?, timestamp? | POST /v1/notes |
| `NoteIngestRequest` | note_id, user_id, content, timestamp | Internal (background task) |
| `NoteSummary` | id, content, created_at?, updated_at? | GET /v1/notes response |

---

## Configuration

All configuration is read from environment variables (loaded from `.env` by `python-dotenv` in `src/core/config.py`).

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt connection string |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password123` | Neo4j password |
| `POSTGRES_DSN` | `postgresql://postgres:postgres@localhost:5432/second_brain` | PostgreSQL connection string |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GOOGLE_API_KEY` | — | Alternative env var for Gemini key |
| `GEMINI_CHAT_MODEL` | `gemini-2.5-flash` | Model name for discovery chat |
| `GEMINI_EMBEDDING_MODEL` | `models/text-embedding-004` | Model name for embeddings |
| `JWT_SECRET_KEY` | `dev-secret-change-me` | HMAC secret for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm (hardcoded) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT expiry & Streamlit session TTL |
| `API_BASE_URL` | `http://0.0.0.0:8000` | Used by Streamlit to locate the API |

---

## Setup & Running

### Prerequisites

- Python ≥3.14 (specified in `.python-version`)
- Docker & Docker Compose (for databases)
- `uv` package manager (`pip install uv` or via pipx)

### 1. Install dependencies

```bash
uv sync
```

### 2. Start databases

```bash
docker compose up -d
# Starts:
#   - Neo4j on ports 7474 (browser) and 7687 (bolt)
#   - PostgreSQL on port 5432
```

### 3. Configure environment

Copy or edit `.env`:

```env
GEMINI_API_KEY=your-google-ai-key   # Optional but recommended
```

### 4. Run the API

```bash
make api
# or: uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The API initializes on startup:
- Creates PostgreSQL connection pool
- Creates `users` table if it does not exist
- Creates Neo4j driver
- Creates uniqueness constraints on `Note.id` and `Chunk.id`
- Creates the vector index on `Chunk.embedding`

### 5. Run the UI

```bash
make ui
# or: API_BASE_URL=http://localhost:8000 uv run streamlit run ui/app.py
```

### All-in-one (dev mode)

```bash
make dev
```

### Stop

```bash
make down   # docker compose down
```

### Makefile Commands

| Command | Action |
|---------|--------|
| `make db` | `docker compose up -d` |
| `make api` | Start FastAPI dev server on port 8000 |
| `make ui` | Start Streamlit UI (reads `API_BASE_URL` env) |
| `make dev` | Start db + api + ui all together |
| `make down` | `docker compose down` |

---

## Key Implementation Details

### Text Chunking (`src/utils.py:chunk_text`)

Notes are split into **500-character overlapping slices** (100-char overlap). This preserves context across chunk boundaries and ensures each chunk is small enough for embedding limits.

```
[Note: 1200 characters]
  Chunk 0: chars 0-499
  Chunk 1: chars 400-899
  Chunk 2: chars 800-1199
```

### Embedding Strategy (`src/routes/notes.py:get_embeddings`)

1. If `GEMINI_API_KEY` is set: calls `genai.embed_content()` with `task_type="retrieval_document"` for each chunk concurrently via `asyncio.gather`.
2. If Gemini returns an empty embedding for a chunk (rate limit, error), falls back to mock embedding for that chunk.
3. If no Gemini key is available: uses `get_mock_embedding()` for all chunks.

**Mock embedding algorithm** (`src/utils.py:get_mock_embedding`):
- Tokenize into lowercase alphanumeric words
- For each token, compute SHA-256 → take first 4 bytes → mod 1536 → increment that dimension
- L2-normalize the resulting vector
- This is **deterministic** — same text always produces the same vector

### Background Ingestion (`src/routes/notes.py:process_and_index_note`)

Runs via FastAPI `BackgroundTasks`. The timeline is:
1. POST returns immediately with `{"status": "queued", "note_id": "..."}` — the Note node is already MERGED into Neo4j at this point.
2. Background task: chunks text, generates embeddings, deletes old Chunks for this note, MERGEs new Chunks, re-creates `[:HAS_CHUNK]` relationships.
3. Re-indexing is **idempotent** — re-saving the same note replaces its chunks.

### Discovery / Relationship Analysis (`src/routes/notes.py:discover_relationships`)

Uses **Server-Sent Events (SSE)** to stream Gemini's response:
1. Fetches selected notes from Neo4j (or all user notes if no `note_ids` filter).
2. Formats notes as markdown blocks: `### Title\nbody`.
3. Sends to Gemini with a system prompt ("Identify connections, overlaps, dependencies, actionable insights").
4. Streams tokens back as SSE: `data: {"text": "<token>"}\n\n`.
5. If the configured chat model (`gemini-2.5-flash`) is unavailable, automatically falls back through `gemini-1.5-flash`, `-8b`, `-pro`, `-1.0-pro`, or any model that supports `generateContent`.

### Authentication Flow

1. User registers → password is bcrypt-hashed → stored in PostgreSQL → JWT created with HS256 (sub=user_id, email, exp=now+30min).
2. User logins → password verified → JWT returned.
3. All `/v1/notes/*` endpoints require the JWT via FastAPI dependency `get_current_user`:
   - Extracts `Authorization: Bearer <token>` via OAuth2PasswordBearer
   - Decodes and verifies JWT
   - Fetches user from PostgreSQL by `sub` (user_id)
   - Returns user dict or raises 401

### Session Management (Streamlit)

Streamlit runs as a single-page app. Session is managed via:
- **URL query params:** `?sid=<random16>` — identifies the browser tab
- **In-memory dict** `_SESSION_CACHE` — maps session IDs to auth data (with TTL)
- **`st.session_state`** — holds active auth data during page interactions
- On page reload: `hydrate_auth_from_store()` restores auth from `_SESSION_CACHE` by looking up `sid`
- On logout or expiry: both are cleared

### Docker Compose Topology

| Container | Image | Ports | Volumes | Credentials |
|-----------|-------|-------|---------|-------------|
| `ai_engine_graph` | `neo4j:5.18.0` | 7474 (HTTP), 7687 (Bolt) | `neo4j_data`, `neo4j_logs` | `neo4j` / `password123` |
| `ai_engine_auth_db` | `postgres:16` | 5432 | `postgres_data` | `postgres` / `postgres`, db: `second_brain` |

Both databases use named Docker volumes for persistence across container restarts.

### Security Notes

- Passwords are hashed with bcrypt (72-byte limit enforced).
- JWT secret defaults to `dev-secret-change-me` — **change in production**.
- No ORM — raw SQL/cypher throughout.
- No built-in rate limiting.
- CORS is not explicitly configured (FastAPI default allows all origins in dev).
- Gemini API key is read from env only — not exposed to clients.

---

## Quick Start Example

```bash
# 1. Install
uv sync

# 2. Start databases
docker compose up -d

# 3. Set your Gemini key (optional)
echo "GEMINI_API_KEY=your-key" >> .env

# 4. Run API + UI
make dev
# API at http://localhost:8000
# UI at http://localhost:8501

# 5. Register via curl
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret123"}'

# 6. Add a note
curl -X POST http://localhost:8000/v1/notes \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"content":"My test note\n\nThis is the body of the note."}'

# 7. List notes
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/v1/notes?limit=10"

# 8. Discover relationships (stream)
curl -N -H "Authorization: Bearer <token>" \
  "http://localhost:8000/v1/notes/discover?limit=5"
```
# smart-notebook
