#!/usr/bin/env python3
"""
Build training corpus for insurance-ai from:
  1. HuggingFace datasets (pre-labeled, read from local extracted JSONL files)
  2. GitHub repos (actuarial/insurance Python code, chunked by function/class)

Output: data/training_corpus.jsonl
Schema per record:
  {
    "id":       str,
    "type":     "qa" | "structured_data" | "code" | "text" | "multi_turn",
    "source":   "huggingface" | "github",
    "dataset":  str,           # dataset or repo name
    "content":  str,           # text used for embedding
    "metadata": dict           # all original fields preserved
  }
"""

import os
import sys
import json
import ast
import uuid
import hashlib
from pathlib import Path
from datetime import datetime

# ── Paths ────────────────────────────────────────────────────────────────────

HF_DIR        = Path("/home/ubuntu/insurance-llm/data/huggingface/extracted")
GITHUB_DIR    = Path("/home/ubuntu/insurance-llm/data/github_repos_full")
OUTPUT_PATH   = Path("/home/ubuntu/insurance-ai/data/training_corpus.jsonl")

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_id(prefix: str, value: str) -> str:
    h = hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{prefix}_{h}"


def write_record(fh, record: dict):
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── HuggingFace dataset handlers ─────────────────────────────────────────────

def build_content_actuarial_exam(row: dict) -> str:
    parts = []
    if row.get("instruction"):
        parts.append(f"Q: {row['instruction']}")
    if row.get("response"):
        parts.append(f"A: {row['response'][:3000]}")
    if row.get("exam"):
        parts.append(f"Exam: {row['exam']}")
    return "\n".join(parts)


def build_content_bitext(row: dict) -> str:
    parts = []
    if row.get("category"):
        parts.append(f"Category: {row['category']}")
    if row.get("intent"):
        parts.append(f"Intent: {row['intent']}")
    if row.get("instruction"):
        parts.append(f"Q: {row['instruction']}")
    if row.get("response"):
        parts.append(f"A: {row['response']}")
    return "\n".join(parts)


def build_content_fraud(row: dict) -> str:
    return (
        f"Insurance fraud record: country={row.get('country','')}, "
        f"year={row.get('year','')}, "
        f"claim_amount=${row.get('claim_amount_usd',''):.2f}, "
        f"claim_type={row.get('claim_type','')}, "
        f"fraud_label={row.get('fraud_label','')}, "
        f"fraud_scheme={row.get('fraud_scheme_type','')}, "
        f"fraud_probability={row.get('fraud_probability',0):.4f}, "
        f"detection_method={row.get('detection_method','')}, "
        f"duplicate_flag={row.get('duplicate_claim_flag','')}, "
        f"reporting_delay_days={row.get('reporting_delay_days','')}, "
        f"policy_duration_months={row.get('policy_duration_months','')}."
    )


def build_content_underwriting(row: dict) -> str:
    return (
        f"Underwriting application: policy_type={row.get('policy_type','')}, "
        f"risk_class={row.get('risk_class','')}, "
        f"risk_score={row.get('risk_score','')}, "
        f"approved={row.get('approved','')}, "
        f"premium_multiplier={row.get('premium_multiplier','')}, "
        f"applicant_age={row.get('applicant_age','')}, "
        f"credit_score={row.get('credit_score','')}, "
        f"claims_history={row.get('claims_history_count','')}, "
        f"coverage_requested=${row.get('coverage_amount_requested',0):.0f}."
    )


def build_content_insurance_qa_en(row: dict) -> str:
    parts = []
    if row.get("topic_en"):
        parts.append(f"Topic: {row['topic_en']}")
    if row.get("question_en"):
        parts.append(f"Q: {row['question_en']}")
    return "\n".join(parts)


def build_content_insurance_qa_v2(row: dict) -> str:
    parts = []
    if row.get("input"):
        parts.append(f"Q: {row['input']}")
    if row.get("output"):
        parts.append(f"A: {row['output'][:3000]}")
    return "\n".join(parts)


def build_content_mortality(row: dict) -> str:
    if row.get("instruction") and row.get("response"):
        return f"Q: {row['instruction']}\nA: {row['response'][:3000]}"
    # fallback: key numeric fields as text
    fields = ["country", "year", "age_group", "gender", "mortality_rate_per_1000",
              "life_expectancy_years", "loss_ratio_pct", "solvency_ratio",
              "actuarial_quality_class", "product_type"]
    parts = [f"{k}={row[k]}" for k in fields if row.get(k) is not None]
    return "Mortality record: " + ", ".join(parts)


def build_content_multi_turn(row: dict) -> str:
    parts = []
    parts.append(f"Task: {row.get('task','')}")
    if row.get("company name"):
        parts.append(f"Company: {row['company name']} — {row.get('company description','')[:500]}")
    if row.get("lob"):
        parts.append(f"Line of business: {row['lob']}")
    # Extract final assistant answer from trace
    trace = row.get("trace", [])
    for msg in reversed(trace):
        if msg.get("role") == "assistant" and msg.get("type") == "user-facing assistant":
            content = msg.get("content", "")
            if content and len(content) > 20:
                parts.append(f"Answer: {content[:2000]}")
                break
    if row.get("reference answer"):
        parts.append(f"Reference: {row['reference answer']}")
    return "\n".join(parts)


HF_DATASETS = {
    "actuarial_exam":        ("qa",              build_content_actuarial_exam),
    "bitext_insurance":      ("qa",              build_content_bitext),
    "fraud_detection":       ("structured_data", build_content_fraud),
    "underwriting":          ("structured_data", build_content_underwriting),
    "insurance_qa_en":       ("qa",              build_content_insurance_qa_en),
    "insurance_qa_v2":       ("qa",              build_content_insurance_qa_v2),
    "mortality_data":        ("text",            build_content_mortality),
    "multi_turn_underwriting": ("multi_turn",    build_content_multi_turn),
}


def process_hf_datasets(fh) -> int:
    total = 0
    for dataset_name, (record_type, builder) in HF_DATASETS.items():
        jsonl_path = HF_DIR / f"{dataset_name}.jsonl"
        if not jsonl_path.exists():
            print(f"  [WARN] Missing: {jsonl_path}")
            continue

        count = 0
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    content = builder(row).strip()
                    if not content or len(content) < 10:
                        continue

                    # Trim content to 8000 chars for embedding
                    content = content[:8000]

                    record = {
                        "id":       make_id(dataset_name[:6], line),
                        "type":     record_type,
                        "source":   "huggingface",
                        "dataset":  dataset_name,
                        "content":  content,
                        "metadata": row,
                    }
                    write_record(fh, record)
                    count += 1
                except (json.JSONDecodeError, Exception):
                    continue

        print(f"  {dataset_name:<30} {count:>7,} records")
        total += count
    return total


# ── GitHub repo handlers ──────────────────────────────────────────────────────

# File extensions to process
CODE_EXTS  = {".py", ".ipynb"}
DOC_EXTS   = {".md", ".rst", ".txt"}
SKIP_DIRS  = {"__pycache__", ".git", ".tox", "node_modules", "venv", ".venv",
              "dist", "build", "egg-info", ".eggs", "htmlcov", ".pytest_cache"}


def chunk_python_file(source: str, filepath: str) -> list[dict]:
    """
    Extract top-level functions and classes from a Python file.
    Each chunk = one function or class definition with its docstring + body.
    Falls back to splitting by logical blocks if AST parsing fails.
    """
    chunks = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fall back: split into ~100-line chunks
        lines = source.splitlines()
        for i in range(0, len(lines), 100):
            block = "\n".join(lines[i:i + 100]).strip()
            if len(block) > 50:
                chunks.append({"text": block, "name": f"block_{i//100}"})
        return chunks

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Only top-level and first-level class methods
            if not isinstance(node, ast.ClassDef):
                # Skip nested functions beyond first level
                pass
            try:
                start = node.lineno - 1
                end   = node.end_lineno
                body  = "\n".join(source.splitlines()[start:end])
                if len(body.strip()) < 30:
                    continue
                docstring = ast.get_docstring(node) or ""
                chunks.append({
                    "text":      body[:6000],
                    "name":      node.name,
                    "docstring": docstring[:500],
                    "kind":      type(node).__name__,
                })
            except Exception:
                continue

    # If no chunks found, treat entire file as one chunk
    if not chunks and len(source.strip()) > 50:
        chunks.append({"text": source[:6000], "name": "module", "docstring": "", "kind": "module"})

    return chunks


def chunk_doc_file(source: str) -> list[dict]:
    """Split markdown/rst/text by headings or paragraphs into chunks."""
    chunks = []
    paragraphs = source.split("\n\n")
    current = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        current.append(para)
        # Flush when we hit ~500 chars
        combined = "\n\n".join(current)
        if len(combined) >= 500:
            chunks.append({"text": combined[:6000]})
            current = []
    if current:
        combined = "\n\n".join(current).strip()
        if len(combined) > 50:
            chunks.append({"text": combined[:6000]})
    return chunks


def process_github_repos(fh) -> int:
    total = 0
    if not GITHUB_DIR.exists():
        print(f"  [WARN] GitHub repos directory not found: {GITHUB_DIR}")
        return 0

    repos = sorted([d for d in GITHUB_DIR.iterdir() if d.is_dir()])
    for repo_dir in repos:
        repo_name = repo_dir.name
        repo_count = 0

        for filepath in repo_dir.rglob("*"):
            # Skip unwanted directories
            if any(skip in filepath.parts for skip in SKIP_DIRS):
                continue
            if not filepath.is_file():
                continue

            ext = filepath.suffix.lower()
            if ext not in CODE_EXTS and ext not in DOC_EXTS:
                continue

            try:
                source = filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path = str(filepath.relative_to(GITHUB_DIR))

            if ext == ".py":
                chunks = chunk_python_file(source, str(filepath))
                for chunk in chunks:
                    content = (
                        f"# {repo_name} — {rel_path}\n"
                        f"# {chunk.get('kind','')}: {chunk.get('name','')}\n"
                    )
                    if chunk.get("docstring"):
                        content += f'"""{chunk["docstring"]}"""\n'
                    content += chunk["text"]
                    content = content[:8000]

                    record = {
                        "id":      make_id("gh", f"{rel_path}:{chunk.get('name','')}"),
                        "type":    "code",
                        "source":  "github",
                        "dataset": repo_name,
                        "content": content,
                        "metadata": {
                            "repo":      repo_name,
                            "filepath":  rel_path,
                            "language":  "python",
                            "name":      chunk.get("name", ""),
                            "kind":      chunk.get("kind", ""),
                            "docstring": chunk.get("docstring", ""),
                        },
                    }
                    write_record(fh, record)
                    repo_count += 1

            elif ext == ".ipynb":
                # Extract code and markdown cells from notebooks
                try:
                    nb = json.loads(source)
                    for cell in nb.get("cells", []):
                        cell_type = cell.get("cell_type", "")
                        src = "".join(cell.get("source", []))
                        if not src.strip() or len(src) < 30:
                            continue
                        content = (
                            f"# Notebook: {repo_name} — {rel_path}\n"
                            f"# Cell type: {cell_type}\n"
                            f"{src[:8000]}"
                        )
                        record = {
                            "id":      make_id("nb", f"{rel_path}:{src[:40]}"),
                            "type":    "code" if cell_type == "code" else "text",
                            "source":  "github",
                            "dataset": repo_name,
                            "content": content[:8000],
                            "metadata": {
                                "repo":      repo_name,
                                "filepath":  rel_path,
                                "language":  "python" if cell_type == "code" else "markdown",
                                "cell_type": cell_type,
                            },
                        }
                        write_record(fh, record)
                        repo_count += 1
                except Exception:
                    continue

            elif ext in DOC_EXTS:
                chunks = chunk_doc_file(source)
                for chunk in chunks:
                    content = f"# {repo_name} — {rel_path}\n{chunk['text']}"
                    record = {
                        "id":      make_id("doc", f"{rel_path}:{chunk['text'][:40]}"),
                        "type":    "text",
                        "source":  "github",
                        "dataset": repo_name,
                        "content": content[:8000],
                        "metadata": {
                            "repo":     repo_name,
                            "filepath": rel_path,
                            "language": ext.lstrip("."),
                        },
                    }
                    write_record(fh, record)
                    repo_count += 1

        if repo_count:
            print(f"  {repo_name:<45} {repo_count:>6,} chunks")
        total += repo_count

    return total


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print("BUILD TRAINING CORPUS")
    print(f"{'='*60}")
    print(f"Output: {OUTPUT_PATH}")
    print()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.now()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:

        # ── HuggingFace ──
        print("HuggingFace datasets:")
        hf_total = process_hf_datasets(fh)
        print(f"  {'SUBTOTAL':<30} {hf_total:>7,}\n")

        # ── GitHub ──
        print("GitHub repos:")
        gh_total = process_github_repos(fh)
        print(f"  {'SUBTOTAL':<45} {gh_total:>6,}\n")

    elapsed = (datetime.now() - start).total_seconds()
    grand_total = hf_total + gh_total

    # Verify line count
    with open(OUTPUT_PATH) as f:
        line_count = sum(1 for _ in f)

    print(f"{'='*60}")
    print("DONE")
    print(f"{'='*60}")
    print(f"HuggingFace records : {hf_total:>8,}")
    print(f"GitHub chunks       : {gh_total:>8,}")
    print(f"Total               : {grand_total:>8,}")
    print(f"Lines in file       : {line_count:>8,}")
    print(f"Output file size    : {OUTPUT_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"Time elapsed        : {elapsed:.1f}s")

    # Write metadata
    meta = {
        "total_records":  line_count,
        "hf_records":     hf_total,
        "github_chunks":  gh_total,
        "created":        datetime.now().isoformat(),
        "output":         str(OUTPUT_PATH),
    }
    meta_path = OUTPUT_PATH.parent / "corpus_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Metadata            : {meta_path}")


if __name__ == "__main__":
    main()
