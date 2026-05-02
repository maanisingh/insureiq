# InsureIQ — Full System Blueprint

## Overview

InsureIQ is a multi-tenant AI SaaS platform for insurance professionals.
Backend: FastAPI (Python). Frontend: Next.js 16 (TypeScript).
AI: AutoGen 0.4+ multi-agent team on AWS Bedrock.

---

## Backend — `insurance-ai/`

### Tech Stack
- FastAPI + Uvicorn (port 8000)
- PostgreSQL 15 (port 5433) — psycopg2
- Redis 7 (port 6379) — session cache
- Qdrant (port 6333) — global knowledge base (insurance_global, 547K records)
- Qdrant (port 7333) — per-user workspace collections
- AWS Bedrock Titan (embeddings, 1536-dim)
- AWS Bedrock Claude (generation — model per agent, see below)
- AutoGen 0.4+ SelectorGroupChat — 5 specialist agents

### API Endpoints

```
Authentication
  POST /auth/register          → register user, return JWT
  POST /auth/login             → authenticate, return JWT
  POST /auth/refresh           → renew JWT (24h)
  GET  /auth/me                → current user profile
  PATCH /auth/me               → update name/email/password
  DELETE /auth/me              → delete account (cascade)
  POST /auth/forgot-password   → generate reset token
  POST /auth/reset-password    → consume token, set new password

Workspaces
  GET    /workspaces           → list user's workspaces
  POST   /workspaces           → create workspace
  GET    /workspaces/{id}      → get workspace
  DELETE /workspaces/{id}      → delete (cascade all data)

Policies
  GET    /policies?workspace_id=  → list policies
  POST   /policies                → create policy (auto policy_number)
  GET    /policies/{id}           → get with full policy_data JSONB
  PATCH  /policies/{id}           → update policy_data
  DELETE /policies/{id}           → delete

Chat
  POST /chat                   → full response (sync)
  POST /chat/stream            → SSE streaming response
                                 Body: { workspace_id, session_id?, message,
                                         preferred_agent?, enabled_sources? }
                                 SSE events: routing, tool_call, token, done, error
  POST /chat/session           → create session, return session_id
  GET  /chat/history           → sessions list (with first_message preview) or
                                 messages for a specific session_id

Search
  POST /search                 → dual search (global + workspace)
  GET  /search/global          → global Qdrant only
  GET  /search/workspace/{id}  → workspace Qdrant only

Uploads
  POST   /uploads              → multipart upload (async extraction)
  GET    /uploads              → list uploads with status
  GET    /uploads/{id}         → detail (extraction_status, chunk_count)
  DELETE /uploads/{id}         → delete file + Qdrant vectors + DB row

API Keys
  POST   /api-keys             → generate key (returns raw key ONCE)
  GET    /api-keys             → list user's keys (prefix only)
  DELETE /api-keys/{id}        → revoke key

Generated Documents (new)
  GET    /gen-docs?workspace_id=         → list summaries (id, title, doc_type, word_count, indexed_at, created_at)
  GET    /gen-docs/{id}?workspace_id=    → full document including content
  DELETE /gen-docs/{id}?workspace_id=    → delete DB row + Qdrant vectors (metadata.doc_id filter)
```

### Chat Request Schema

```python
class ChatMessage(BaseModel):
    workspace_id:     str
    session_id:       str | None = None
    message:          str
    preferred_agent:  str | None = None   # force a specific agent (None = auto-route)
    enabled_sources:  list[str] | None = None
    # Supported source keys: "rag", "workspace", "web", "regulations", "huggingface"
    # None = all sources enabled
```

### Authentication
- JWT Bearer tokens (HS256, 24h expiry)
- API keys (`ak_` prefix) accepted on all protected endpoints
- `get_current_user()` checks both JWT and API key paths

### Database Schema (PostgreSQL)

```
users                 — id, email, password_hash, full_name, is_active, is_verified
workspaces            — id, user_id→users, name, description
policies              — id, workspace_id→workspaces, policy_number UNIQUE, policy_type, policy_data JSONB, status
chat_history          — id, workspace_id→workspaces, session_id, messages JSONB, created_at
uploads               — id, workspace_id→workspaces, filename, file_type, file_size,
                        extraction_status, extracted_text, chunk_count, indexed_at
generated_documents   — id, workspace_id→workspaces, title, doc_type, content TEXT,
                        word_count, metadata JSONB, indexed_at, created_at
                        (created by PolicyAgent + UnderwritingAgent; auto-indexed to Qdrant :7333)
password_reset_tokens — id, user_id→users, token_hash UNIQUE, expires_at, used_at
api_keys              — id, user_id→users, name, key_prefix, key_hash UNIQUE, is_active, last_used_at
```

### Multi-Agent System

AutoGen `SelectorGroupChat` — 5 specialist agents, each with its own Claude model.
`enabled_sources` filters which tools each agent has access to per request.
`preferred_agent` adds a mandatory routing instruction to the task prefix.

```
Selector (Haiku 4.5, max_tokens=50)
  → reads query, picks agent from participants list

RAGAgent (Haiku 4.5)
  Tools (filtered by enabled_sources):
    "rag"       → search_global_knowledge
    "workspace" → search_workspace_documents, list_workspace_policies,
                  get_policy_details, list_uploaded_documents

ResearchAgent (Sonnet 4.5)
  Tools (filtered by enabled_sources):
    "web"         → web_search, search_insurance_news, fetch_public_rate_data
    "regulations" → search_insurance_regulations
    "huggingface" → search_huggingface_datasets, download_and_index_dataset

PricingAgent (Sonnet 4.6)
  Tools (always available — no source filter):
    calculate_auto_premium (ISO), calculate_workers_comp_premium (NCCI),
    calculate_life_premium (SOA VBT), run_actuarial_code (Python sandbox),
    calculate_loss_reserve (chain ladder)

PolicyAgent (Opus 4.6)
  Tools (always available):
    create_insurance_policy
    generate_policy_document (40-page ISO)
      → saves to generated_documents table
      → chunks + embeds + indexes to Qdrant :7333 via app/core/doc_indexer.py

UnderwritingAgent (Sonnet 4.5)
  Tools (always available):
    assess_risk_score, check_underwriting_appetite
    generate_underwriting_memo
      → saves to generated_documents table
      → chunks + embeds + indexes to Qdrant :7333 via app/core/doc_indexer.py
```

### Data Flows

**Training corpus ingestion:**
`scripts/build_dataset.py` → `data/training_corpus.jsonl` (547K records)
`scripts/index.py` → Bedrock Titan embed → Qdrant :6333 `insurance_global`

**Chat (SSE stream):**
User message → `POST /chat/stream`
  → apply preferred_agent routing hint (if set)
  → build_insurance_team(workspace_id, enabled_sources)
  → load history from Redis/PostgreSQL
  → AutoGen SelectorGroupChat.run_stream()
  → SSE events: routing, tool_call, token, done
  → persist to Redis + PostgreSQL

**Document upload:**
`POST /uploads` → save to disk → BackgroundTask:
  extractor.py (format→Bedrock) → chunker.py → embed × N → Qdrant :7333

### Infrastructure (Docker Compose)
```
insurance-postgres         — postgres:15, port 5433
insurance-redis            — redis:7-alpine, port 6379
insurance-qdrant-global    — qdrant/qdrant, port 6333/6334
insurance-qdrant-workspace — qdrant/qdrant, port 7333/7334
```

### Workspace Isolation
- Every PostgreSQL query: `WHERE workspace_id = %s AND user_id = %s`
- Qdrant workspace: separate collection `workspace_{uuid}` on port 7333
- DELETE user → CASCADE → all workspaces, policies, uploads, chat_history

### Running Backend
```bash
cd insurance-ai
docker compose up -d
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Frontend — `insureiq-frontend/`

### Tech Stack
- Next.js 16 (App Router) + TypeScript
- Tailwind CSS + shadcn/ui (base-ui primitives — NOT radix-ui)
- @assistant-ui/react (LocalRuntime + Thread component)
- next-auth v5 beta (Credentials provider → FastAPI, trustHost: true)
- Zustand (persisted: workspace, session, source toggles, agent preference, token usage)
- TanStack Query (API caching + polling)
- next-themes (dark/light/system)
- Lucide React (icons)

### Route Structure
```
Chat        → /chat         MessageSquare
Documents   → /documents    FileText       (AI-generated docs: policy docs, UW memos)
Uploads     → /uploads      Upload         (file uploads to workspace knowledge base)
Settings    → /settings     Settings
```

### Chat Page Layout
```
┌─ top bar ──────────────────────────────────────────────────────┐
│ [Price a risk] [Draft...] [Check appetite] ...  [Agent] [Chats]│
├─ semantic search bar (always visible) ─────────────────────────┤
│ [Both|Global KB|My Docs]  🔍 [query input]  [Search]  [×]     │
│ ┌── results panel (shown after search, max-h-56, scrollable) ─┐│
│ │ 94% · Global · flood zone pricing...                        ││
│ └──────────────────────────────────────────────────────────────┘│
├─ Thread (fills remaining height) ──────────────────────────────┤
│  [chat messages + tool call groups + markdown]                 │
│  ┌─ composer ─────────────────────────────────────────────────┐│
│  │ [+] [RAG][My Docs][Web][Regs][HF] | [Auto▾]        [↑]   ││
│  └────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────┘
```

### Composer Controls (next to + attachment button)
Source toggle pills (multi-select, persisted):
- **RAG** — global 547K knowledge base
- **My Docs** — workspace uploaded documents
- **Web** — live internet search + industry news
- **Regs** — insurance regulations & compliance
- **HF** — HuggingFace datasets

Agent selector pill (single-select, persisted):
- **Auto** (default) — SelectorGroupChat routes automatically
- **RAGAgent** — force knowledge base + docs
- **ResearchAgent** — force web/dataset research
- **PricingAgent** — force actuarial pricing
- **PolicyAgent** — force policy creation/generation
- **UnderwritingAgent** — force risk assessment

### Key Files
```
auth.ts                              — next-auth: Credentials→FastAPI, trustHost:true
middleware.ts                        — protect dashboard routes
lib/types.ts                         — TypeScript interfaces (ChatSession has first_message)
lib/api.ts                           — typed fetch client for all endpoints
lib/insureiq-adapter.ts              — ChatModelAdapter: SSE→assistant-ui, sends
                                       preferred_agent + enabled_sources, tracks token est.
lib/utils.ts                         — cn(), formatBytes(), formatDate(), truncate()
store/index.ts                       — Zustand: workspace/session, sourcesEnabled,
                                       preferredAgent, tokenUsage
app/providers.tsx                    — SessionProvider + QueryClient + ThemeProvider + Toaster
app/api/chat/stream/route.ts         — SSE proxy route (unused by adapter — adapter calls API directly)
components/chat/InsureIQRuntimeProvider.tsx  — AssistantRuntimeProvider + AgentStatusContext
components/chat/AgentBadge.tsx       — colour-coded agent badges (5 agents)
components/chat/ChatSearchBar.tsx    — persistent semantic search bar in chat page
components/chat/ComposerSources.tsx  — source toggle pills + agent selector in composer
components/layout/Sidebar.tsx        — nav (Chat, Documents, Uploads, Settings)
components/assistant-ui/thread.tsx   — Thread with ComposerSources wired into ComposerAction
```

### Auth Flow
1. User submits login → `signIn("credentials", { email, password })`
2. next-auth calls `POST http://localhost:8000/auth/login`
3. Returns `access_token` → stored in JWT session as `session.access_token`
4. All API calls: `Authorization: Bearer ${session.access_token}`
5. `trustHost: true` in auth.ts + `AUTH_TRUST_HOST=true` in .env.local

### Chat Streaming Flow
```
User message → assistant-ui LocalRuntime
  → InsureIQAdapter.run()
    → reads sourcesEnabled + preferredAgent from store
    → POST ${NEXT_PUBLIC_API_URL}/chat/stream
      body: { workspace_id, session_id, message, preferred_agent, enabled_sources }
    → FastAPI: build_insurance_team(workspace_id, enabled_sources)
      → SelectorGroupChat.run_stream(task)
        → SSE: routing(agent), tool_call, token, done(agent_used)
    → adapter: yields tokens progressively to assistant-ui
    → routing event → AgentStatusContext → AgentStatusBadge in top bar
    → done event → addTokenUsage(est_input, est_output) to Zustand
```

### Semantic Search Flow (ChatSearchBar)
```
User types query in ChatSearchBar → clicks Search / presses Enter
  → api.search.both/global/workspace() → GET or POST /search endpoint
  → results rendered in scrollable panel above thread
  → × button clears results, collapses panel
  → thread always visible below
```

### Chat History
- Sessions stored in PostgreSQL `chat_history` table
- `GET /chat/history?workspace_id=` returns sessions with:
  - `session_id`, `created_at`, `message_count`
  - `first_message` — content of first message (used as session title)
- History modal: shows first message as title + date + message count
- Session switch: uses `router.refresh()` (not `window.location.reload()`)

### Token Usage (Settings)
- Estimated per-request: input = `ceil(userText.length / 4)` tokens
- Stored in Zustand (persisted to localStorage) — resets on reset button
- Displayed in Settings > Token Usage card with 4 metrics:
  input tokens, output tokens, total tokens, estimated cost (~$0.006/1K blended)

### Settings Page Sections
1. **Appearance** — Light / Dark / System theme
2. **Account** — Email + Name (read-only)
3. **Token Usage** — estimated token consumption + cost + reset button
4. **API Keys** — create/list/revoke + expandable usage docs

### Running Frontend
```bash
cd insureiq-frontend
npm run dev      # development
npm run build    # production build
npm start        # serve production
```

---

## Wire-Up Summary

```
User Action                    Frontend                    Backend
─────────────────────────────────────────────────────────────────────────
Register                     → POST /api/auth/callback    → POST /auth/register ✓
Login                        → next-auth Credentials      → POST /auth/login ✓
Send chat message            → InsureIQAdapter.run()      → POST /chat/stream (SSE) ✓
  with source toggles        → enabled_sources in body    → filters agent tools ✓
  with agent selector        → preferred_agent in body    → routing hint in task ✓
Semantic search (chat bar)   → api.search.*               → GET/POST /search* ✓
Generate policy document in chat  → PolicyAgent.generate_policy_document() → saved to generated_documents + indexed to Qdrant :7333 ✓
Generate UW memo in chat          → UnderwritingAgent.generate_underwriting_memo() → saved to generated_documents + indexed to Qdrant :7333 ✓
View generated documents          → api.generatedDocs.list/get()  → GET /gen-docs ✓
Download document as PDF          → window.print() (browser-native, no library) ✓
Delete generated document         → api.generatedDocs.delete()    → DELETE /gen-docs/{id} + Qdrant vectors ✓
Upload document              → fetch POST /uploads        → POST /uploads ✓
Poll upload status           → useQuery refetchInterval   → GET /uploads ✓
List policies                → useQuery                   → GET /policies ✓
Create policy                → useMutation                → POST /policies ✓
Chat history                 → api.chat.history()         → GET /chat/history ✓
  first_message preview      → ChatSession.first_message  → SQL: messages->0->>'content' ✓
Session switch               → router.refresh()           → (local state) ✓
Track token usage            → addTokenUsage() in adapter → (client-side estimate) ✓
Generate API key             → api.apiKeys.create()       → POST /api-keys ✓
/search route                → redirect("/chat")          → N/A ✓
```

---

## Environment Variables

### Backend (`insurance-ai/config/.env`)
```
DB_HOST, DB_PORT (5433), DB_PASSWORD, DB_NAME, DB_USER
SECRET_KEY, JWT_EXPIRE_HOURS (24)
REDIS_HOST, REDIS_PORT (6379), REDIS_DB, REDIS_PASSWORD
AWS_REGION (us-east-1), AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
QDRANT_HOST, QDRANT_PORT (6333), QDRANT_WORKSPACE_PORT (7333)
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
FRONTEND_URL=http://localhost:3000
```

### Frontend (`insureiq-frontend/.env.local`)
```
AUTH_SECRET=<random-32-char-string>
AUTH_TRUST_HOST=true
NEXTAUTH_URL=https://ai.cipherx.co.uk        (production)
NEXT_PUBLIC_API_URL=https://ai.cipherx.co.uk/api  (production)
API_URL=http://localhost:8000                (server-side nextauth calls)
```

---

## Anti-Hallucination Guarantees

- **Pricing**: every output cites ISO, NCCI, or SOA source + shows exact formula
- **Policy documents**: ISO standard form language only, disclaimer on every doc
- **Underwriting**: every decision cites the specific factor triggering it
- **Code execution**: sandboxed subprocess, 30s timeout, no network/filesystem access
- **RAG sources**: every chat response returns `sources[]` with `layer: global|workspace`
- **Source toggles**: user controls which knowledge sources the agents use per message

---

## Test Results

### Backend: 140 passing across 3 test suites

#### Suite 1 — Core API (77 tests, ~60s)
```
pytest tests/test_auth.py tests/test_workspaces.py tests/test_api_keys.py
       tests/test_policies.py tests/test_search.py tests/test_uploads.py
       tests/test_chat.py tests/test_agents.py -k "not TestMultiAgent"

tests/test_auth.py        — 19 tests: register, login, reset password, JWT, profile CRUD
tests/test_workspaces.py  — 7 tests: CRUD, isolation
tests/test_api_keys.py    — 7 tests: create, authenticate on all endpoints, revoke
tests/test_policies.py    — 7 tests: CRUD, policy number format POL-XXXXXXXX
tests/test_search.py      — 6 tests: global + workspace + dual search, result shape
tests/test_uploads.py     — 9 tests: all formats, extraction, deletion, wrong workspace
tests/test_chat.py        — 9 tests: session create, chat response, history, auth
tests/test_agents.py      — 22 tests: pricing accuracy, UW accuracy, policy doc generation
                            (deterministic — no Bedrock calls)
```

#### Suite 2 — Comprehensive Functional (58 passed, 1 skipped, ~10 min)
```
pytest tests/test_comprehensive.py -m "not live"

TestInfrastructure (6)      — health, PostgreSQL, Redis, Qdrant global 547K+, workspace Qdrant, generated_documents table
TestRAGQuality (6)          — real content returned for auto/NCCI/fraud/ISO queries, scores >0.5
TestPricingAccuracy (10)    — ISO age factors, NCCI loss costs, SOA VBT, smoker>nonsmoker, CAS chain ladder, Python sandbox
TestUnderwritingAccuracy (7) — tier classification, ISO penalty factors, appetite guideline text, memo structure
TestPolicyDocumentQuality (6) — all 7 ISO sections, min length, standard exclusions, anti-hallucination disclaimer
TestGeneratedDocumentPipeline (7) — save to DB, index to Qdrant, API retrieval, full content, workspace search, delete
TestUploadPipeline (5)      — txt accepted, unsupported rejected, extraction+chunks, workspace search, delete
TestChatSessionManagement (7) — response content, session_id, agent_used, history, first_message, preferred_agent routing
TestAPIKeys (5)             — create, authenticate on /search, list shows prefix only, revoke blocks access
```

#### Suite 3 — Live Bedrock Agent Routing (5 tests, ~10 min)
```
pytest tests/test_comprehensive.py -m live

test_live_rag_agent_knowledge_question  — RAGAgent answers claims-made vs occurrence; cites knowledge base
test_live_pricing_agent_auto_premium    — PricingAgent produces ISO-cited auto premium calculation
test_live_pricing_agent_wc_ncci         — PricingAgent produces NCCI WC calculation with loss cost rate
test_live_underwriting_agent_risk_score — UnderwritingAgent produces risk score with tier classification
test_live_research_agent_finds_datasets — ResearchAgent searches HuggingFace for insurance datasets
```

### Frontend: 26/26 Playwright E2E passing
```
Landing Page (2)            — hero, nav, agents, stats, CTA; nav links
Auth Pages (3)              — login, register, forgot-password forms
API Integration (11)        — register/login/profile; workspaces; API keys; policies CRUD;
                              SSE chat; SSE with preferred_agent+enabled_sources; semantic
                              search; chat history first_message; generated docs endpoint;
                              document upload; health
Dashboard authenticated (10) — chat page (quick actions + search bar + composer);
                               semantic search real search + dismiss; /policies→/documents;
                               documents page (AI docs UI, filter pills); uploads (dropzone);
                               /search→/chat; settings (token usage + docs);
                               no Policies/Search sidebar; sidebar nav; history modal
```

### Bugs fixed during testing
```
agents/insurance_agent.py   — asyncio.get_event_loop() fails in Python 3.13 threadpools
                              → replaced with asyncio.new_event_loop() + asyncio.set_event_loop()
agents/bedrock_client.py    — Bedrock ValidationException: text content blocks must be non-empty
                              → added guards on UserMessage, FunctionExecutionResultMessage content
```

### Admin Demo Account
```
URL:      https://ai.cipherx.co.uk
Email:    admin@cipherx.co.uk
Password: InsureIQ2026!Admin

Pre-loaded with:
  5 chat sessions   — RAG, WC Pricing, UW Risk Assessment, Research (HuggingFace), + existing
  2 generated docs  — Commercial GL Policy Document (POL-782B7AE7) + UW Declination Memo
  7 uploaded files  — Workers Comp Manual, Commercial Property, Auto Guide, Life Insurance,
                      UW Guidelines, ISO CGL Coverage Form, NCCI WC Rate Tables
  57 Qdrant vectors — all content indexed and searchable
```

### Running All Tests
```bash
cd /home/ubuntu/insurance-ai
source venv/bin/activate

# Suite 1: Core API tests (~60s)
python3 -m pytest tests/test_auth.py tests/test_workspaces.py tests/test_api_keys.py \
  tests/test_policies.py tests/test_search.py tests/test_uploads.py \
  tests/test_chat.py tests/test_agents.py -k "not TestMultiAgent" -q

# Suite 2: Comprehensive functional tests (~10 min)
python3 -m pytest tests/test_comprehensive.py -m "not live" -q

# Suite 3: Live Bedrock agent routing (~10 min)
python3 -m pytest tests/test_comprehensive.py -m live -q

# Frontend E2E
cd /home/ubuntu/insureiq-frontend
npx playwright test --reporter=list

# Re-seed admin account (if reset needed)
cd /home/ubuntu/insurance-ai && source venv/bin/activate
python3 scripts/seed_admin.py
```
tests/test_api_keys.py     — API key generation, auth, revocation
tests/test_auth.py         — register, login, reset password, profile
tests/test_workspaces.py   — CRUD, isolation
tests/test_policies.py     — CRUD, policy number format
tests/test_mcp_servers.py  — health checks for all 7 MCP servers
tests/test_search.py       — global + workspace search
tests/test_uploads.py      — all formats, extraction, deletion
```

### Frontend: 26/26 Playwright E2E passing
```
Landing Page (2)           — hero, nav, agents, stats, CTA; nav links
Auth Pages (3)             — login, register, forgot-password forms
API Integration (11)       — register/login/profile; workspaces; API keys;
                             policies CRUD; SSE chat; SSE with preferred_agent
                             + enabled_sources; semantic search endpoints;
                             chat history first_message; generated documents
                             endpoint; document upload
Dashboard authenticated (10) — chat page (quick actions + search bar + composer);
                               semantic search runs real search + dismisses;
                               /policies redirects to /documents;
                               documents page (AI-generated docs, filter pills);
                               uploads page (dropzone);
                               /search redirects to /chat; settings (token usage +
                               expandable docs); no Policies/Search sidebar links;
                               sidebar navigation (Documents + Uploads + Settings);
                               chat history modal
```

---

## Start Everything

```bash
# 1. Start infrastructure
cd /home/ubuntu/insurance-ai
docker compose up -d

# 2. Start backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Start frontend (separate terminal)
cd /home/ubuntu/insureiq-frontend
npm run dev

# 4. Open browser
# https://ai.cipherx.co.uk  ← InsureIQ app (production)
# http://localhost:3000      ← development
# http://localhost:8000/docs ← Backend Swagger UI
```

---

## PM2 Production Processes

```bash
pm2 list                     # view both processes
pm2 restart insureiq-backend  # after Python file changes
pm2 restart insureiq-frontend # after Next.js build
pm2 save                      # persist process list
```
