"""
Text chunker — splits extracted document text into embedding-ready chunks.

Strategy:
  - Split on double-newlines (paragraph boundaries) first.
  - Merge short paragraphs until each chunk is ~800 characters.
  - Hard-split paragraphs longer than MAX_CHARS.
  - Each chunk carries metadata for Qdrant payload.
"""

from __future__ import annotations

MAX_CHARS   = 1500   # max characters per chunk
TARGET_CHARS = 800   # target characters per chunk


def chunk_text(
    text:       str,
    upload_id:  str,
    workspace_id: str,
    filename:   str,
) -> list[dict]:
    """Split text into chunks suitable for embedding.

    Args:
        text:         Extracted document text.
        upload_id:    UUID of the uploads row.
        workspace_id: UUID of the workspace.
        filename:     Original filename for metadata.

    Returns:
        List of dicts: {text, metadata: {upload_id, workspace_id, filename, chunk_index, total_chunks}}
    """
    paragraphs = _split_paragraphs(text)
    chunks     = _merge_paragraphs(paragraphs)

    results = []
    for i, chunk_text in enumerate(chunks):
        results.append({
            "text": chunk_text.strip(),
            "metadata": {
                "upload_id":    upload_id,
                "workspace_id": workspace_id,
                "filename":     filename,
                "chunk_index":  i,
            },
        })

    # Backfill total_chunks
    total = len(results)
    for item in results:
        item["metadata"]["total_chunks"] = total

    return results


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; hard-split paragraphs over MAX_CHARS."""
    raw = [p.strip() for p in text.split("\n\n") if p.strip()]
    out = []
    for para in raw:
        if len(para) <= MAX_CHARS:
            out.append(para)
        else:
            # Hard-split at sentence boundaries or fixed width
            sentences = para.replace(". ", ".\n").split("\n")
            buf = []
            for sent in sentences:
                buf.append(sent)
                if sum(len(s) for s in buf) >= MAX_CHARS:
                    out.append(" ".join(buf))
                    buf = []
            if buf:
                out.append(" ".join(buf))
    return out


def _merge_paragraphs(paragraphs: list[str]) -> list[str]:
    """Merge short paragraphs to approach TARGET_CHARS per chunk."""
    chunks = []
    buf    = []
    buf_len = 0

    for para in paragraphs:
        if buf_len + len(para) > MAX_CHARS and buf:
            chunks.append("\n\n".join(buf))
            buf     = []
            buf_len = 0
        buf.append(para)
        buf_len += len(para)
        if buf_len >= TARGET_CHARS:
            chunks.append("\n\n".join(buf))
            buf     = []
            buf_len = 0

    if buf:
        chunks.append("\n\n".join(buf))

    return [c for c in chunks if c.strip()]
