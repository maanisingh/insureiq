"""
Research tools — web search, HuggingFace dataset discovery, dataset download & indexing.

Used by: ResearchAgent
"""

import os
import json
import time
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")


def search_web(query: str, limit: int = 6) -> str:
    """Search the internet for insurance information, regulations, news, and market data.

    Args:
        query: Search query string.
        limit: Number of results to return (default 6).

    Returns:
        Formatted search results with titles, snippets, and URLs.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
        resp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=headers,
            timeout=15,
            follow_redirects=True,
        )
        soup    = BeautifulSoup(resp.text, "html.parser")
        results = soup.find_all("div", class_="result", limit=limit)

        if not results:
            return f"No web results found for: '{query}'"

        lines = [f"## Web Search Results: '{query}'\n"]
        for i, r in enumerate(results, 1):
            title_tag   = r.find("a", class_="result__a")
            snippet_tag = r.find("a", class_="result__snippet")
            title   = title_tag.get_text(strip=True)   if title_tag   else "No title"
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else "No snippet"
            url     = title_tag.get("href", "")        if title_tag   else ""
            lines.append(f"**[{i}] {title}**")
            lines.append(snippet)
            if url:
                lines.append(f"URL: {url}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Web search error: {e}"


def search_insurance_news(topic: str, limit: int = 5) -> str:
    """Search for the latest insurance industry news, regulatory updates, and market trends.

    Args:
        topic: Insurance topic to search news for (e.g. 'flood insurance rates 2025').
        limit: Number of news results (default 5).

    Returns:
        Latest news results with headlines and summaries.
    """
    return search_web(f"insurance {topic} news 2025", limit=limit)


def search_insurance_regulations(topic: str, jurisdiction: str = "US") -> str:
    """Search for insurance regulations, compliance requirements, and regulatory filings.

    Args:
        topic:        Regulatory topic (e.g. 'workers compensation rate filing').
        jurisdiction: Country or state (default 'US').

    Returns:
        Regulatory search results.
    """
    return search_web(f"insurance regulations {topic} {jurisdiction} official", limit=5)


def search_huggingface_datasets(query: str, limit: int = 8) -> str:
    """Search HuggingFace Hub for insurance, actuarial, or financial datasets.

    Args:
        query: Dataset search query (e.g. 'insurance claims fraud detection').
        limit: Number of results to return (default 8).

    Returns:
        List of matching datasets with descriptions, sizes, and download commands.
    """
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        datasets = list(api.list_datasets(search=query, limit=limit, sort="downloads"))

        if not datasets:
            return f"No HuggingFace datasets found for: '{query}'"

        lines = [f"## HuggingFace Datasets: '{query}'\n"]
        for i, ds in enumerate(datasets, 1):
            did     = ds.id
            tags    = ", ".join(ds.tags[:5]) if ds.tags else "none"
            lines.append(f"**[{i}] {did}**")
            lines.append(f"Tags: {tags}")
            lines.append(f"Download: `from datasets import load_dataset; ds = load_dataset('{did}')`")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"HuggingFace search error: {e}"


def download_and_index_dataset(dataset_id: str, workspace_id: str, split: str = "train", max_rows: int = 5000) -> str:
    """Download a dataset from HuggingFace and index it into the user's workspace
    so it can be used for pricing models, analysis, or RAG queries.

    Args:
        dataset_id:   HuggingFace dataset ID (e.g. 'insurance-data/claims').
        workspace_id: The user's workspace UUID to index into.
        split:        Dataset split to use ('train', 'test', etc.).
        max_rows:     Maximum rows to index (default 5000 to avoid overload).

    Returns:
        Confirmation with number of chunks indexed.
    """
    try:
        from datasets import load_dataset
        from app.core.bedrock import embed_query
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        import uuid as _uuid

        # Download dataset
        print(f"Downloading {dataset_id} ({split} split, max {max_rows} rows)...")
        ds = load_dataset(dataset_id, split=split, trust_remote_code=True)

        # Convert to text chunks
        chunks_indexed = 0
        collection     = f"workspace_{workspace_id}"
        qdrant          = QdrantClient(
            host=os.getenv("QDRANT_WORKSPACE_HOST", "localhost"),
            port=int(os.getenv("QDRANT_WORKSPACE_PORT", "7333")),
        )
        existing_cols = {c.name for c in qdrant.get_collections().collections}
        if collection not in existing_cols:
            qdrant.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

        points = []
        for i, row in enumerate(ds):
            if i >= max_rows:
                break
            # Convert row to text
            text = " | ".join(f"{k}: {v}" for k, v in row.items() if v is not None)[:2000]
            if len(text) < 20:
                continue
            try:
                vector = embed_query(text)
                points.append(PointStruct(
                    id=str(_uuid.uuid4()),
                    vector=vector,
                    payload={
                        "text":     text,
                        "type":     "dataset",
                        "metadata": {
                            "dataset_id":   dataset_id,
                            "workspace_id": workspace_id,
                            "row_index":    i,
                            "source":       "huggingface",
                        },
                    },
                ))
            except Exception:
                continue

            # Batch upsert every 50
            if len(points) >= 50:
                qdrant.upsert(collection_name=collection, points=points)
                chunks_indexed += len(points)
                points = []

        if points:
            qdrant.upsert(collection_name=collection, points=points)
            chunks_indexed += len(points)

        return (
            f"✓ Dataset '{dataset_id}' downloaded and indexed.\n"
            f"  Rows processed: {min(i+1, max_rows)}\n"
            f"  Vectors indexed to workspace: {chunks_indexed}\n"
            f"  You can now query this data via workspace search."
        )
    except Exception as e:
        return f"Dataset download/index error: {e}"


def fetch_public_rate_data(line_of_business: str, state: str = "national") -> str:
    """Search for publicly available insurance rate data, loss ratios, and industry statistics.

    Args:
        line_of_business: Insurance line (e.g. 'auto', 'homeowners', 'workers_comp').
        state:            State or 'national' for aggregate data.

    Returns:
        Summary of publicly available rate and loss data.
    """
    query = f"{line_of_business} insurance rate data loss ratio statistics {state} NAIC"
    return search_web(query, limit=5)
