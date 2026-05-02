"""
Shared AWS Bedrock client utilities.

Provides three capabilities:
- embed_query()      : Bedrock Titan (1536-dim) for vector embeddings
- generate()         : Bedrock Claude 3.5 Sonnet for chat generation
- extract_document() : Bedrock Claude 3.5 Sonnet for document text extraction
"""

import os
import json
import base64
import boto3
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")

AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY        = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET     = os.getenv("AWS_SECRET_ACCESS_KEY")

EMBED_MODEL    = "amazon.titan-embed-text-v1"
CHAT_MODEL     = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
VECTOR_SIZE    = 1536

INSURANCE_SYSTEM_PROMPT = """You are an expert insurance AI assistant with deep knowledge in:
- Underwriting (risk assessment, policy pricing, appetite)
- Claims (investigation, settlement, fraud detection)
- Actuarial science (mortality tables, loss reserves, pricing models)
- Insurance regulation (compliance, solvency, consumer protection)
- Policy interpretation (coverage, exclusions, endorsements)
- Reinsurance and risk transfer

Always provide accurate, professional responses. Cite sources when available.
If you are uncertain, say so clearly rather than guessing."""


@lru_cache(maxsize=1)
def _bedrock_client():
    kwargs = {"region_name": AWS_REGION}
    if AWS_KEY and AWS_SECRET:
        kwargs["aws_access_key_id"]     = AWS_KEY
        kwargs["aws_secret_access_key"] = AWS_SECRET
    return boto3.client("bedrock-runtime", **kwargs)


def embed_query(text: str) -> list[float]:
    """Embed text using Bedrock Titan (1536-dim).

    Args:
        text: Text to embed (truncated to 8000 chars).

    Returns:
        1536-dimensional float vector.
    """
    client = _bedrock_client()
    resp = client.invoke_model(
        modelId=EMBED_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text[:8000]}),
    )
    return json.loads(resp["body"].read())["embedding"]


def generate(
    messages: list[dict],
    system: str = INSURANCE_SYSTEM_PROMPT,
    context_docs: list[dict] | None = None,
    max_tokens: int = 2048,
) -> str:
    """Generate a response using Bedrock Claude 3.5 Sonnet.

    Args:
        messages:     Conversation history [{role, content}].
        system:       System prompt.
        context_docs: Optional RAG context documents [{text, source, score}].
        max_tokens:   Max tokens in response.

    Returns:
        Response text string.
    """
    client = _bedrock_client()

    # Build context block prepended to the last user message
    if context_docs:
        context_parts = []
        global_docs   = [d for d in context_docs if d.get("layer") == "global"]
        workspace_docs = [d for d in context_docs if d.get("layer") == "workspace"]

        if global_docs:
            context_parts.append("## Insurance Knowledge Base")
            for i, doc in enumerate(global_docs[:5], 1):
                src  = doc.get("source", "knowledge base")
                text = doc.get("text", "")[:600]
                context_parts.append(f"[{i}] ({src})\n{text}")

        if workspace_docs:
            context_parts.append("\n## Your Workspace Documents")
            for i, doc in enumerate(workspace_docs[:3], 1):
                src  = doc.get("title", doc.get("source", "uploaded document"))
                text = doc.get("text", "")[:600]
                context_parts.append(f"[{i}] ({src})\n{text}")

        context_block = "\n\n".join(context_parts)

        # Inject context into the last user message
        augmented = list(messages)
        if augmented and augmented[-1]["role"] == "user":
            augmented[-1] = {
                "role": "user",
                "content": (
                    f"Context:\n{context_block}\n\n"
                    f"Question: {augmented[-1]['content']}"
                ),
            }
        messages = augmented

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }

    resp   = client.invoke_model(
        modelId=CHAT_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    result = json.loads(resp["body"].read())
    return result["content"][0]["text"]


def extract_document(content_bytes: bytes, media_type: str, filename: str) -> str:
    """Extract and structure text from a document using Bedrock Claude 3.5 Sonnet.

    Supported media types:
        application/pdf           → native document message (best quality)
        text/plain                → raw text → Bedrock structures it
        application/vnd.openxmlformats-officedocument.* → pre-extracted text
        text/csv                  → pre-extracted text

    Args:
        content_bytes: Raw file bytes (or pre-extracted text bytes for non-PDF).
        media_type:    MIME type string.
        filename:      Original filename (used in prompt context).

    Returns:
        Extracted and structured text string.
    """
    client = _bedrock_client()

    if media_type == "application/pdf":
        # Claude 3.5 Sonnet supports PDF natively via base64 document message
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.b64encode(content_bytes).decode(),
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Extract all text content from this document '{filename}'. "
                            "Preserve section headings, tables (as markdown), lists, and key data. "
                            "Output only the extracted content, no commentary."
                        ),
                    },
                ],
            }],
        }
    else:
        # Non-PDF: content_bytes is already plain text (pre-processed by extractor.py)
        text = content_bytes.decode("utf-8", errors="ignore")
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{
                "role": "user",
                "content": (
                    f"The following is the raw content of '{filename}' ({media_type}).\n"
                    "Clean, structure, and extract the key information. "
                    "Preserve all important data, headings, and tables as markdown.\n\n"
                    f"{text[:20000]}"
                ),
            }],
        }

    resp   = client.invoke_model(
        modelId=CHAT_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    result = json.loads(resp["body"].read())
    return result["content"][0]["text"]
