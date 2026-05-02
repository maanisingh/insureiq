# InsureIQ

AI-powered insurance platform built on AWS Bedrock, AutoGen multi-agent system, and a Next.js frontend.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS, assistant-ui |
| Backend | FastAPI (Python), PostgreSQL 15, Redis 7 |
| AI | AWS Bedrock Claude (5 specialist agents via AutoGen SelectorGroupChat) |
| Vector DB | Qdrant × 2 (global 547K record KB + per-workspace) |
| Auth | next-auth v5 (Credentials) + JWT + API keys |
| Infra | Docker Compose, PM2, nginx |

## Agents

| Agent | Model | Purpose |
|---|---|---|
| RAGAgent | Claude Haiku 4.5 | Insurance knowledge base + document search |
| ResearchAgent | Claude Sonnet 4.5 | Web search, HuggingFace datasets, regulations |
| PricingAgent | Claude Sonnet 4.6 | ISO auto, NCCI workers comp, SOA life, Python actuarial |
| PolicyAgent | Claude Opus 4.6 | ISO standard policy document generation (40+ pages) |
| UnderwritingAgent | Claude Sonnet 4.5 | Risk scoring, appetite checks, UW memos |

## Quick start

### Backend
```bash
cd backend
docker compose up -d
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env   # fill in secrets
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local           # fill in secrets
npm run dev
```

## CD

Push to `main` → GitHub Actions → SSH deploy to production.

**Required GitHub Secrets:**
- `SERVER_HOST` — production server hostname
- `SSH_PRIVATE_KEY` — SSH private key for the `ubuntu` user

## Tests

```bash
# Backend (fast, ~60s)
cd backend && source venv/bin/activate
pytest tests/ -k "not TestMultiAgent and not live" -q

# Backend live Bedrock tests (~10 min)
pytest tests/test_comprehensive.py -m live -q

# Frontend E2E
cd frontend && npx playwright test
```

## Docs

Full system blueprint: [`BLUEPRINT.md`](./BLUEPRINT.md)
