#!/usr/bin/env python3
"""
Index training corpus into Qdrant (insurance_global) using AWS Bedrock Titan.

Usage:
    python scripts/index.py [--limit N] [--workers 10] [--batch 100] [--reset]

Features:
    - AWS Bedrock Titan embeddings (1536-dim, matches MCP server expectations)
    - Credentials loaded from config/.env
    - Concurrent requests via ThreadPoolExecutor
    - Resumable: skips already-indexed records by offset
    - Progress reporting with ETA
"""

import os
import sys
import json
import uuid
import argparse
import concurrent.futures
from pathlib import Path
from datetime import datetime
from threading import Lock
from dotenv import load_dotenv

# Load env from config/.env
ENV_PATH = Path(__file__).parent.parent / "config" / ".env"
load_dotenv(ENV_PATH)

import boto3
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams

# ── Config ───────────────────────────────────────────────────────────────────

CORPUS_PATH    = Path(__file__).parent.parent / "data" / "training_corpus.jsonl"
COLLECTION     = "insurance_global"
VECTOR_SIZE    = 1536
BEDROCK_MODEL  = "amazon.titan-embed-text-v1"

QDRANT_HOST    = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT    = int(os.getenv("QDRANT_PORT", "6333"))

AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY        = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET     = os.getenv("AWS_SECRET_ACCESS_KEY")

# ── Clients ──────────────────────────────────────────────────────────────────

def make_bedrock():
    kwargs = {"region_name": AWS_REGION}
    if AWS_KEY and AWS_SECRET:
        kwargs["aws_access_key_id"]     = AWS_KEY
        kwargs["aws_secret_access_key"] = AWS_SECRET
    return boto3.client("bedrock-runtime", **kwargs)


def make_qdrant():
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


# ── Collection setup ─────────────────────────────────────────────────────────

def ensure_collection(client: QdrantClient, reset: bool = False) -> int:
    """Create collection if needed; return current vector count."""
    collections = {c.name for c in client.get_collections().collections}

    if reset and COLLECTION in collections:
        client.delete_collection(COLLECTION)
        print(f"  Deleted existing collection '{COLLECTION}'")
        collections.discard(COLLECTION)

    if COLLECTION not in collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"  Created collection '{COLLECTION}' (size={VECTOR_SIZE}, COSINE)")
        return 0

    info = client.get_collection(COLLECTION)
    count = info.points_count or 0
    print(f"  Collection '{COLLECTION}' exists — {count:,} vectors already indexed")
    return count


# ── Embedding ────────────────────────────────────────────────────────────────

def embed(bedrock, text: str) -> list[float] | None:
    try:
        resp = bedrock.invoke_model(
            modelId=BEDROCK_MODEL,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text[:8000]}),
        )
        return json.loads(resp["body"].read())["embedding"]
    except Exception as e:
        return None


# ── Indexing ─────────────────────────────────────────────────────────────────

def run(limit: int | None, workers: int, batch_size: int, reset: bool):
    print(f"\n{'='*60}")
    print("INDEX TRAINING CORPUS → QDRANT (Bedrock Titan)")
    print(f"{'='*60}")
    print(f"Corpus   : {CORPUS_PATH}")
    print(f"Qdrant   : {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Model    : {BEDROCK_MODEL} ({VECTOR_SIZE}-dim)")
    print(f"Workers  : {workers}")
    print(f"Batch    : {batch_size}")
    print(f"Limit    : {limit or 'ALL'}")
    print()

    # Validate corpus
    if not CORPUS_PATH.exists():
        print(f"ERROR: Corpus not found at {CORPUS_PATH}")
        print("Run scripts/build_dataset.py first.")
        sys.exit(1)

    # Connect
    print("Connecting...")
    qdrant  = make_qdrant()
    bedrock = make_bedrock()
    print("  Qdrant  : ok")
    print("  Bedrock : ok")
    print()

    # Collection
    start_offset = ensure_collection(qdrant, reset=reset)
    print()

    # Count total lines
    print("Counting corpus lines...")
    with open(CORPUS_PATH) as f:
        total_lines = sum(1 for _ in f)
    print(f"  Total records : {total_lines:,}")
    if limit:
        target = min(limit, total_lines - start_offset)
    else:
        target = total_lines - start_offset
    print(f"  To index now  : {target:,}")
    if target <= 0:
        print("\nNothing to index.")
        return
    print()

    # ── Main loop ──
    print(f"{'='*60}")
    print("INDEXING")
    print(f"{'='*60}")

    start_time = datetime.now()
    indexed    = 0
    skipped    = 0
    errors     = 0
    lock       = Lock()
    batch_data: list[dict] = []

    def flush_batch(data: list[dict]):
        nonlocal indexed, errors
        texts   = [d["content"] for d in data]
        records = data

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            embeddings = list(pool.map(lambda t: embed(bedrock, t), texts))

        points = []
        for rec, emb in zip(records, embeddings):
            if emb is None:
                with lock:
                    errors += 1
                continue
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "text":     rec["content"][:2000],
                    "title":    rec.get("dataset", ""),
                    "source":   rec.get("source", ""),
                    "type":     rec.get("type", ""),
                    "metadata": rec.get("metadata", {}),
                },
            ))

        if points:
            qdrant.upsert(collection_name=COLLECTION, points=points)
            with lock:
                indexed += len(points)

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f):
            # Skip already-indexed records
            if line_num < start_offset:
                skipped += 1
                continue
            # Honour limit
            if limit and (indexed + len(batch_data)) >= limit:
                break

            line = line.strip()
            if not line:
                continue

            try:
                rec = json.loads(line)
                if not rec.get("content") or len(rec["content"]) < 10:
                    continue
                batch_data.append(rec)
            except json.JSONDecodeError:
                errors += 1
                continue

            if len(batch_data) >= batch_size:
                flush_batch(batch_data)
                batch_data = []

                # Progress
                total_done = start_offset + indexed
                elapsed    = (datetime.now() - start_time).total_seconds()
                rate       = indexed / elapsed if elapsed > 0 else 0
                remaining  = target - indexed
                eta_min    = (remaining / rate / 60) if rate > 0 else 0
                pct        = (total_done / total_lines * 100)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"{total_done:>7,}/{total_lines:>7,} ({pct:5.1f}%) | "
                    f"this run: {indexed:>6,} | {rate:>5.0f}/sec | "
                    f"ETA: {eta_min:.0f}m | errors: {errors}"
                )

    # Flush remainder
    if batch_data:
        flush_batch(batch_data)

    # Final stats
    elapsed   = (datetime.now() - start_time).total_seconds()
    try:
        final_count = qdrant.get_collection(COLLECTION).points_count
    except Exception:
        final_count = "?"

    print(f"\n{'='*60}")
    print("COMPLETE")
    print(f"{'='*60}")
    print(f"Indexed this run : {indexed:,}")
    print(f"Errors           : {errors}")
    print(f"Total in Qdrant  : {final_count}")
    print(f"Time             : {elapsed/60:.1f} min")
    print(f"Rate             : {indexed/elapsed:.0f} vec/sec" if elapsed > 0 else "")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Index insurance corpus into Qdrant via Bedrock Titan")
    parser.add_argument("--limit",   type=int,   default=None, help="Max records to index (default: all)")
    parser.add_argument("--workers", type=int,   default=10,   help="Concurrent Bedrock threads (default: 10)")
    parser.add_argument("--batch",   type=int,   default=100,  help="Records per batch (default: 100)")
    parser.add_argument("--reset",   action="store_true",      help="Delete and recreate the Qdrant collection")
    args = parser.parse_args()

    run(limit=args.limit, workers=args.workers, batch_size=args.batch, reset=args.reset)


if __name__ == "__main__":
    main()
