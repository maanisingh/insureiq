import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

from app.routers import auth, workspaces, policies, chat, search, uploads, api_keys, generated_docs


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Insurance AI API starting up...")
    # Verify infrastructure is reachable
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5433"),
            database=os.getenv("DB_NAME", "insurance_ai"),
            user=os.getenv("DB_USER", "insurance_ai"),
            password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
        )
        # Ensure generated_documents table exists (idempotent)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS generated_documents (
                id           UUID      PRIMARY KEY DEFAULT uuid_generate_v4(),
                workspace_id UUID      REFERENCES workspaces(id) ON DELETE CASCADE,
                title        VARCHAR(255),
                doc_type     VARCHAR(100),
                content      TEXT      NOT NULL,
                word_count   INTEGER   DEFAULT 0,
                metadata     JSONB     DEFAULT '{}'::jsonb,
                indexed_at   TIMESTAMP,
                created_at   TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_gendocs_workspace
                ON generated_documents(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_gendocs_type
                ON generated_documents(workspace_id, doc_type);
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("  PostgreSQL: OK")
    except Exception as e:
        print(f"  PostgreSQL: WARNING - {e}")

    try:
        import redis as _redis
        r = _redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        )
        r.ping()
        print("  Redis: OK")
    except Exception as e:
        print(f"  Redis: WARNING - {e}")

    try:
        from qdrant_client import QdrantClient
        q = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
        q.get_collections()
        print("  Qdrant global: OK")
    except Exception as e:
        print(f"  Qdrant global: WARNING - {e}")

    yield
    print("Insurance AI API shutting down...")


app = FastAPI(
    title="Insurance AI API",
    description="Backend API for Insurance AI Agent — RAG, MCP, Bedrock",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — read allowed origins from env; defaults to localhost for dev
_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080")
cors_origins  = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,           prefix="/auth",       tags=["Authentication"])
app.include_router(workspaces.router,     prefix="/workspaces", tags=["Workspaces"])
app.include_router(policies.router,       prefix="/policies",   tags=["Policies"])
app.include_router(chat.router,           prefix="/chat",       tags=["Chat"])
app.include_router(search.router,         prefix="/search",     tags=["Search"])
app.include_router(uploads.router,        prefix="/uploads",    tags=["Uploads"])
app.include_router(api_keys.router,       prefix="/api-keys",   tags=["API Keys"])
app.include_router(generated_docs.router, prefix="/gen-docs",   tags=["Generated Documents"])


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "healthy", "service": "Insurance AI API", "version": "1.0.0"}


@app.get("/", tags=["System"])
def root():
    return {"message": "Insurance AI API v1.0.0", "docs": "/docs", "health": "/health"}
