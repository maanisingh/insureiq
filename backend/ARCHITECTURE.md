# Insurance AI Platform — Full Architecture

## Overview

A multi-tenant insurance AI SaaS backend. Each user gets isolated workspaces,
can manage policies, upload documents, and chat with an AI agent that answers
insurance questions using two layers of RAG knowledge — a shared global
knowledge base and their own private workspace documents.

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI + Uvicorn | REST backend, port 8000 |
| Auth | PyJWT (HS256, 24h expiry) + bcrypt | Authentication |
| Relational DB | PostgreSQL 15 (port 5433) | Users, workspaces, policies, uploads, chat history |
| Session cache | Redis 7 (port 6379) | Hot chat history, 30-day TTL |
| Global vector store | Qdrant (port 6333) | Shared insurance knowledge base |
| Workspace vector store | Qdrant (port 7333) | Per-user uploaded document vectors |
| Embeddings | AWS Bedrock Titan (`amazon.titan-embed-text-v1`) | 1536-dim vectors |
| Generation | AWS Bedrock Claude 3.5 Sonnet v2 | Chat responses |
| Document extraction | AWS Bedrock Claude 3.5 Sonnet v2 | PDF/DOCX/TXT/CSV/Excel → structured text |
| Agent tools | FastMCP (7 MCP servers) | Structured tool interface for AI agents |

---

## Directory Structure

```
insurance-ai/
├── agents/
│   └── insurance_agent.py        # Core RAG agent (embed→search→generate→persist)
├── app/
│   ├── core/
│   │   ├── bedrock.py            # embed_query(), generate(), extract_document()
│   │   ├── extractor.py          # Format-specific doc extraction → Bedrock
│   │   └── chunker.py            # Paragraph-aware text chunking (~800 chars)
│   ├── routers/
│   │   ├── auth.py               # Register, login, refresh, reset password, profile
│   │   ├── workspaces.py         # Workspace CRUD
│   │   ├── policies.py           # Policy CRUD
│   │   ├── chat.py               # Chat endpoint → agent
│   │   ├── search.py             # Semantic search (global + workspace)
│   │   └── uploads.py            # File upload → background extract → index
│   ├── schemas/                  # Pydantic request/response models
│   │   ├── auth.py
│   │   ├── workspaces.py
│   │   ├── policies.py
│   │   ├── chat.py
│   │   ├── search.py
│   │   └── uploads.py
│   ├── database.py               # psycopg2 connection helper
│   └── main.py                   # FastAPI app, CORS, startup health checks, router registration
├── config/
│   └── .env                      # All environment variables
├── data/
│   ├── training_corpus.jsonl     # 547,226 records (HuggingFace + GitHub, ~551 MB)
│   └── corpus_metadata.json      # Corpus stats
├── database/
│   └── schema.sql                # Full PostgreSQL DDL (idempotent, IF NOT EXISTS)
├── mcp_servers/
│   ├── graphrag_base/server.py   # Layer 1 search tools (Qdrant :6333)
│   ├── graphrag_workspace/server.py # Layer 2 search + index tools (Qdrant :7333)
│   ├── chat_memory/server.py     # Save/retrieve chat messages (Redis + PostgreSQL)
│   ├── database/server.py        # Read-only SQL query interface
│   ├── policy_ops/server.py      # Policy CRUD tools
│   ├── qdrant_vector/server.py   # Generic dual-Qdrant search interface
│   └── search_tools/server.py    # DuckDuckGo web search
├── scripts/
│   ├── build_dataset.py          # Build training_corpus.jsonl from HF + GitHub sources
│   └── index.py                  # Index corpus into Qdrant (Bedrock Titan, resumable)
├── storage/
│   └── data/uploads/             # Raw uploaded files, organised by workspace_id
├── tests/
│   ├── conftest.py               # Fixtures: client, auth_headers, workspace_id, db
│   ├── test_auth.py              # 19 tests: register, login, reset password, profile
│   ├── test_workspaces.py        # 7 tests: CRUD, isolation
│   ├── test_policies.py          # 8 tests: CRUD, policy number format
│   ├── test_chat.py              # 9 tests: sessions, agent response, history
│   ├── test_search.py            # 6 tests: global, workspace, dual
│   ├── test_uploads.py           # 9 tests: all formats, extraction, deletion
│   └── test_mcp_servers.py       # 7 tests: health check on all MCP servers
├── .gitignore
├── docker-compose.yml            # postgres, redis, qdrant-global, qdrant-workspace
├── pytest.ini
└── requirements.txt
```

---

## Database Schema

### `users`
```sql
id UUID PK, email VARCHAR(255) UNIQUE, password_hash VARCHAR(255),
full_name VARCHAR(255), is_active BOOLEAN DEFAULT TRUE,
is_verified BOOLEAN DEFAULT FALSE,
created_at TIMESTAMP, updated_at TIMESTAMP
```

### `workspaces`
```sql
id UUID PK, user_id UUID → users.id CASCADE,
name VARCHAR(255), description TEXT,
created_at TIMESTAMP, updated_at TIMESTAMP
```

### `policies`
```sql
id UUID PK, workspace_id UUID → workspaces.id CASCADE,
policy_number VARCHAR(100) UNIQUE,
policy_type VARCHAR(50), policy_data JSONB,
status VARCHAR(20) DEFAULT 'active',
created_at TIMESTAMP, updated_at TIMESTAMP
```

### `chat_history`
```sql
id UUID PK, workspace_id UUID → workspaces.id CASCADE,
session_id VARCHAR(100),
messages JSONB DEFAULT '[]',
created_at TIMESTAMP
```
Indexes: (workspace_id), (workspace_id, session_id), (created_at)

### `uploads`
```sql
id UUID PK, workspace_id UUID → workspaces.id CASCADE,
filename VARCHAR(255), original_filename VARCHAR(255),
file_path VARCHAR(500), file_type VARCHAR(50), file_size BIGINT,
extraction_status VARCHAR(20) DEFAULT 'pending',
extracted_text TEXT, chunk_count INT DEFAULT 0,
indexed_at TIMESTAMP, error_message TEXT,
uploaded_at TIMESTAMP
```

### `password_reset_tokens`
```sql
id UUID PK, user_id UUID → users.id CASCADE,
token_hash VARCHAR(255) UNIQUE,
expires_at TIMESTAMP, used_at TIMESTAMP, created_at TIMESTAMP
```

---

## API Endpoints

### Authentication — `/auth`
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register user, auto-create default workspace, return JWT |
| POST | `/auth/login` | Validate credentials, return JWT |
| POST | `/auth/refresh` | Renew JWT (new 24h window) |
| GET | `/auth/me` | Get current user profile |
| PATCH | `/auth/me` | Update full_name, email, password |
| DELETE | `/auth/me` | Delete account (cascades all data) |
| POST | `/auth/forgot-password` | Generate reset token (returns token; email when SMTP configured) |
| POST | `/auth/reset-password` | Consume token, set new password |

### Workspaces — `/workspaces`
| Method | Path | Description |
|---|---|---|
| GET | `/workspaces` | List all workspaces for current user |
| POST | `/workspaces` | Create new workspace |
| GET | `/workspaces/{id}` | Get workspace |
| DELETE | `/workspaces/{id}` | Delete workspace (cascades all data + Qdrant collection) |

### Policies — `/policies`
| Method | Path | Description |
|---|---|---|
| GET | `/policies?workspace_id=` | List policies in workspace |
| POST | `/policies` | Create policy, auto-generate `POL-XXXXXXXX` number |
| GET | `/policies/{id}?workspace_id=` | Get policy with full `policy_data` JSONB |
| PATCH | `/policies/{id}?workspace_id=` | Update `policy_data` |
| DELETE | `/policies/{id}?workspace_id=` | Delete policy |

### Chat — `/chat`
| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Send message → RAG pipeline → Claude 3.5 Sonnet → return `{session_id, response, sources}` |
| POST | `/chat/session` | Create new session, return `session_id` |
| GET | `/chat/history?workspace_id=&session_id=` | With session_id: messages. Without: list of sessions |

### Search — `/search`
| Method | Path | Description |
|---|---|---|
| POST | `/search` | Dual search (global + workspace) |
| GET | `/search/global?query=` | Global knowledge search only |
| GET | `/search/workspace/{id}?query=` | Workspace-specific search only |

### Uploads — `/uploads`
| Method | Path | Description |
|---|---|---|
| POST | `/uploads` | Upload file (multipart), returns immediately, extraction runs in background |
| GET | `/uploads?workspace_id=` | List uploads with extraction status |
| GET | `/uploads/{id}?workspace_id=` | Get upload detail including `chunk_count`, `indexed_at` |
| DELETE | `/uploads/{id}?workspace_id=` | Delete file from disk + Qdrant vectors + DB row |

### System
| Method | Path | Description |
|---|---|---|
| GET | `/health` | `{status: "healthy"}` |
| GET | `/docs` | Swagger UI |

---

## Data Flows

### Flow 1 — Training Data Ingestion (one-time)

```
HuggingFace datasets (8 datasets, 468K records)     GitHub repos (40 repos, 79K chunks)
   fraud_detection, bitext_insurance,                chainladder-python, lifelib,
   actuarial_exam, underwriting,                     FASLR, ifrs17-expert-rag,
   insurance_qa_en/v2, mortality_data,               actuarialmath, aggregate, ...
   multi_turn_underwriting
              │                                               │
              └──────────────────┬────────────────────────────┘
                                 ▼
                    scripts/build_dataset.py
                    → data/training_corpus.jsonl
                      547,226 records
                      {id, type, source, dataset, content, metadata}
                                 │
                                 ▼
                    scripts/index.py
                    batches of 100, 10 concurrent Bedrock calls
                                 │
                                 ▼
                    Bedrock Titan embed-text-v1
                    text[:8000] → 1536-dim float vector
                                 │
                                 ▼
                    Qdrant :6333  insurance_global
                    VectorParams(size=1536, COSINE)
                    payload: {text, title, source, type, metadata}
```

### Flow 2 — User Registration

```
POST /auth/register {email, password, full_name}
       │
       ├─ EmailStr validation + password ≥ 8 chars
       ├─ Check duplicate email (PostgreSQL)
       ├─ bcrypt.hashpw(password, gensalt())
       ├─ INSERT INTO users
       ├─ INSERT INTO workspaces (default workspace auto-created)
       └─ JWT encode({user_id, email, exp: now+24h})
```

### Flow 3 — Document Upload & Workspace Indexing

```
POST /uploads (multipart: workspace_id + file)
       │
       ├─ SYNC: Validate ownership, check extension, enforce 50MB limit
       ├─ SYNC: Save to storage/data/uploads/{workspace_id}/{uuid}.ext
       ├─ SYNC: INSERT INTO uploads (status='pending')
       ├─ SYNC: Return 201 immediately
       │
       └─ BACKGROUND:
              UPDATE uploads SET status='processing'
              │
              extractor.py:
                .pdf  → base64 → Bedrock Claude native PDF document message
                .docx → python-docx text → Bedrock Claude text prompt
                .txt  → raw text → Bedrock Claude text prompt
                .csv  → csv→markdown table → Bedrock Claude text prompt
                .xlsx → openpyxl→markdown tables → Bedrock Claude text prompt
              → structured extracted text
              │
              UPDATE uploads SET extracted_text = text[:100000]
              │
              chunker.py:
                Split on \n\n → merge to ~800 chars → max 1500 chars
                Each chunk: {text, metadata:{upload_id, workspace_id,
                              filename, chunk_index, total_chunks}}
              │
              For each chunk:
                Bedrock Titan embed_query(chunk.text) → 1536-dim vector
                Qdrant :7333  workspace_{workspace_id}  (auto-create if needed)
                PointStruct {id=uuid, vector, payload:{text, type='upload', metadata}}
                Upsert in batches of 50
              │
              UPDATE uploads SET status='done', chunk_count=N, indexed_at=NOW()
```

### Flow 4 — Chat (Core Intelligence Pipeline)

```
POST /chat {workspace_id, session_id?, message}
       │
       ├─ Validate workspace ownership (PostgreSQL)
       ├─ Auto-generate session_id if not provided
       └─ agent.chat(message, workspace_id, session_id, user_id)
              │
              ▼
       STEP 1: embed_query(message) → 1536-dim vector  [Bedrock Titan]
              │
              ▼
       STEP 2: Qdrant :6333  insurance_global
               query_vector=vector, limit=5
               → top-5 global docs [{id, score, text[:800], source, type}]
              │
              ▼
       STEP 3: Qdrant :7333  workspace_{workspace_id}
               (skip if collection doesn't exist)
               query_vector=vector, limit=5
               → top-5 workspace docs [{id, score, text[:800], type, filename}]
              │
              ▼
       STEP 4: Redis LRANGE chat:{workspace_id}:{session_id} -10 -1
               → last 10 messages
               (fallback: PostgreSQL SELECT messages FROM chat_history)
              │
              ▼
       STEP 5: Build Claude messages array:
               [history messages]
               + last message with context injected:
                 "Context:
                  ## Insurance Knowledge Base
                  [1-5] (source) text[:600]...

                  ## Your Workspace Documents
                  [1-3] (filename) text[:600]...

                  Question: {original message}"
              │
              ▼
       STEP 6: Bedrock Claude 3.5 Sonnet v2
               system: "Expert in underwriting, claims, actuarial,
                        regulation, policy interpretation, reinsurance"
               max_tokens: 2048
               → response text
              │
              ▼
       STEP 7: Persist user + assistant messages:
               Redis: RPUSH chat:{workspace_id}:{session_id}, EXPIRE 30 days
               PostgreSQL: UPDATE/INSERT chat_history JSONB array
              │
              ▼
       STEP 8: Build sources (top 3 global + top 2 workspace, deduplicated)
               [{id, score, text[:200], source, layer:"global"|"workspace"}]
              │
              ▼
       Return {session_id, response, sources}
```

### Flow 5 — Search (Direct, No Agent)

```
GET /search/global?query=X
  embed_query(X) → Qdrant :6333 insurance_global → results

GET /search/workspace/{id}?query=X
  ownership check → embed_query(X) → Qdrant :7333 workspace_{id} → results

POST /search {query, workspace_id, limit}
  both simultaneously → {global_results, workspace_results}
```

### Flow 6 — Password Reset

```
POST /auth/forgot-password {email}
  → secrets.token_urlsafe(32) → raw_token
  → hashlib.sha256(raw_token) → token_hash
  → INSERT INTO password_reset_tokens (user_id, token_hash, expires_at=now+1h)
  → return raw_token (email link when SMTP configured)

POST /auth/reset-password {token, new_password}
  → sha256(token) → lookup in password_reset_tokens
  → check: not used, not expired
  → bcrypt new password → UPDATE users SET password_hash
  → UPDATE password_reset_tokens SET used_at=NOW()
```

---

## Storage Responsibilities

| Store | Contents | Key Pattern |
|---|---|---|
| **PostgreSQL :5433** | users, workspaces, policies, chat_history, uploads, password_reset_tokens | UUID primary keys everywhere, FK cascade deletes |
| **Redis :6379** | Chat session messages (hot path, 30-day TTL) | `chat:{workspace_id}:{session_id}` → JSON list |
| **Qdrant :6333** | `insurance_global` — 547K training corpus vectors | 1536-dim Titan, COSINE |
| **Qdrant :7333** | `workspace_{uuid}` — one collection per user workspace | 1536-dim Titan, COSINE, `metadata.upload_id` for targeted deletion |
| **Disk** | Raw uploaded files | `storage/data/uploads/{workspace_id}/{upload_uuid}.ext` |

---

## Workspace Isolation

```
User A
  └── Workspace A (UUID)
        PostgreSQL: all rows WHERE user_id = A and workspace_id = A_ws
        Qdrant :7333: collection "workspace_{A_ws}"  ← physically separate
        Redis: keys "chat:{A_ws}:*"

User B
  └── Workspace B (UUID)
        PostgreSQL: separate rows
        Qdrant :7333: collection "workspace_{B_ws}"  ← physically separate
        Redis: keys "chat:{B_ws}:*"

Enforcement:
  Every endpoint:  WHERE workspace_id = %s AND user_id = %s
  Qdrant search:   collection = f"workspace_{workspace_id}"
                   → Alice's query physically cannot reach Bob's collection
  Delete cascade:  DELETE user → workspaces → policies, uploads, chat_history
  Upload delete:   Filter(metadata.upload_id = X) removes only that doc's vectors
```

---

## MCP Servers (Tool Interface for AI Agents)

| Server | Port | Backend | Tools |
|---|---|---|---|
| `graphrag_base` | 8001 | Qdrant :6333 | `search_global_knowledge`, `get_knowledge_by_id`, `get_collection_stats`, `health_check` |
| `graphrag_workspace` | 8002 | Qdrant :7333 | `search_workspace_knowledge`, `index_document_to_workspace`, `delete_points_by_upload`, `get_workspace_stats`, `delete_workspace_data`, `health_check` |
| `chat_memory` | 8003 | Redis + PostgreSQL | `save_message`, `get_conversation_history`, `retrieve_memories`, `create_session`, `list_sessions`, `health_check` |
| `search_tools` | 8004 | DuckDuckGo | `web_search`, `search_insurance_news`, `search_regulations`, `health_check` |
| `policy_ops` | 8005 | PostgreSQL | `create_policy`, `get_policy`, `list_policies`, `update_policy`, `delete_policy`, `health_check` |
| `database` | 8006 | PostgreSQL (read-only) | `execute_query`, `get_table_info`, `list_tables`, `health_check` |
| `qdrant_vector` | 8007 | Both Qdrant instances | `search_vector_db`, `list_collections`, `get_collection_info`, `health_check` |

All MCP servers use Bedrock Titan (`embed_query`) for semantic search — the same embedding function as the API, no separate embedding path.

Transport: `stdio` (default for agent tool calls) or `--http <port>` (HTTP mode).

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Embedding model | Bedrock Titan `titan-embed-text-v1` (1536-dim) | Consistent across all components; no local GPU needed |
| Generation model | Bedrock Claude 3.5 Sonnet v2 | Best quality; same AWS account as Titan |
| Two Qdrant instances | Port 6333 (global) + 7333 (workspace) | Physical isolation; different scaling profiles |
| Workspace collection naming | `workspace_{uuid}` | Simple, no lookup table needed; UUID is already collision-free |
| Chat persistence | Redis (hot) + PostgreSQL (cold) | Redis for sub-ms retrieval; PostgreSQL for durability + cross-session search |
| Upload processing | FastAPI BackgroundTasks | Returns 201 immediately; extraction is slow (Bedrock calls) |
| JWT expiry | 24h + `/auth/refresh` | Balance between security and UX |
| Password reset | SHA-256 hashed token in DB | Token never stored raw; expiry enforced; single use |
| Chunk size | ~800 chars target, 1500 max | Fits in Titan 8K token limit with room for metadata; granular enough for precise retrieval |

---

## Environment Variables (`config/.env`)

```
# PostgreSQL
DB_HOST, DB_PORT (5433), DB_PASSWORD, DB_NAME, DB_USER

# JWT
SECRET_KEY, JWT_EXPIRE_HOURS (24)

# Redis
REDIS_HOST, REDIS_PORT (6379), REDIS_DB, REDIS_PASSWORD

# AWS Bedrock
AWS_REGION (us-east-1), AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# Qdrant
QDRANT_HOST, QDRANT_PORT (6333)
QDRANT_WORKSPACE_HOST, QDRANT_WORKSPACE_PORT (7333)

# App
CORS_ORIGINS (comma-separated)
FRONTEND_URL (for password reset links)

# Email (when SMTP configured)
MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD
MAIL_FROM, MAIL_FROM_NAME
```

---

## Running the Platform

```bash
# 1. Start infrastructure
cd /home/ubuntu/insurance-ai
docker compose up -d

# 2. Apply database schema (first time)
PGPASSWORD=insurance_secure_2024 psql -h localhost -p 5433 -U insurance_ai -d insurance_ai -f database/schema.sql

# 3. Build training corpus (first time)
source venv/bin/activate
python scripts/build_dataset.py

# 4. Start indexing (runs in background, resumable)
python scripts/index.py --workers 10 --batch 100

# 5. Start API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Run tests
python -m pytest tests/ -v

# 7. Check indexing progress
curl -s http://localhost:6333/collections/insurance_global | \
  python3 -c "import sys,json; d=json.load(sys.stdin)['result']; print('Vectors:', d['points_count'])"
```

---

## Current Status

| Component | Status |
|---|---|
| API (FastAPI, port 8000) | Running |
| PostgreSQL (port 5433) | Running, healthy |
| Redis (port 6379) | Running, healthy |
| Qdrant global (port 6333) | Running, indexing in progress |
| Qdrant workspace (port 7333) | Running, empty until first upload |
| Test suite | 64/64 passing |
| Global index | 169K / 547K vectors (indexing at ~34/sec) |
| Workspace index | Created on first upload per user |
