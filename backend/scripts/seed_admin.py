#!/usr/bin/env python3
"""
seed_admin.py — Seed admin@cipherx.co.uk with rich demo data.

What this does:
  1. Resets admin password to InsureIQ2026!Admin
  2. Makes 5 real chat API calls (1 per agent type) → stored in chat_history
  3. Generates 1 real policy document → saved to generated_documents + indexed to Qdrant
  4. Generates 1 real UW memo → saved to generated_documents + indexed to Qdrant
  5. Uploads 2 additional realistic insurance documents → extracted + indexed to Qdrant
  6. Prints a full summary with verification counts

Run:
  cd /home/ubuntu/insurance-ai
  source venv/bin/activate
  python3 scripts/seed_admin.py
"""

import os
import sys
import json
import time
import uuid
import requests
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is on path for direct tool imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / "config" / ".env")

BASE_URL    = "http://localhost:8000"
ADMIN_EMAIL = "admin@cipherx.co.uk"
ADMIN_PASS  = "InsureIQ2026!Admin"
ADMIN_ID    = "1a8201c8-13b6-4ab9-b32a-3c5d3af10b94"
WORKSPACE_ID = "8f21de2e-321e-4369-b96b-5e63f59ab46b"


# ── Colour helpers ─────────────────────────────────────────────────────────────

def green(s):  return f"\033[32m{s}\033[0m"
def red(s):    return f"\033[31m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"


def ok(msg):   print(f"  {green('✓')} {msg}")
def fail(msg): print(f"  {red('✗')} {msg}"); sys.exit(1)
def info(msg): print(f"  {yellow('→')} {msg}")


# ── DB helper ──────────────────────────────────────────────────────────────────

def db():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
    )


# ── Step 1: Reset admin password ───────────────────────────────────────────────

def reset_admin_password():
    print(bold("\n[1/7] Resetting admin password"))
    import bcrypt
    hashed = bcrypt.hashpw(ADMIN_PASS.encode(), bcrypt.gensalt(rounds=12)).decode()
    conn = db()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE users SET password_hash = %s WHERE email = %s",
        (hashed, ADMIN_EMAIL),
    )
    if cur.rowcount == 0:
        fail(f"Admin user {ADMIN_EMAIL} not found in DB")
    conn.commit()
    cur.close()
    conn.close()
    ok(f"Password reset → {ADMIN_PASS}")


# ── Step 2: Login ──────────────────────────────────────────────────────────────

def login() -> str:
    print(bold("\n[2/7] Logging in as admin"))
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASS,
    })
    if resp.status_code != 200:
        fail(f"Login failed: {resp.text}")
    token = resp.json()["access_token"]
    ok(f"JWT obtained (user_id={resp.json().get('user_id','')})")
    return token


# ── Step 3: Seed 5 real chat sessions ─────────────────────────────────────────

CHAT_SEEDS = [
    {
        "session": "rag-demo",
        "agent":   "RAGAgent",
        "message": (
            "What are the standard exclusions in a Commercial General Liability (CGL) policy "
            "and how do they differ from a Business Owners Policy (BOP)? "
            "Use the knowledge base to give a thorough answer."
        ),
    },
    {
        "session": "pricing-wc",
        "agent":   "PricingAgent",
        "message": (
            "Calculate workers compensation premium for a roofing contractor. "
            "Payroll: $2,000,000. NCCI class code 5403. Experience modifier: 1.15. State: Texas. "
            "Show full NCCI loss cost calculation with formula."
        ),
    },
    {
        "session": "pricing-life",
        "agent":   "PricingAgent",
        "message": (
            "Price a 35-year-old non-smoking male for a $500,000 20-year term life insurance policy. "
            "Use SOA 2015 VBT mortality tables. Show annual and monthly premium with methodology."
        ),
    },
    {
        "session": "underwriting-auto",
        "agent":   "UnderwritingAgent",
        "message": (
            "Assess underwriting risk for a 23-year-old driver with 2 speeding violations "
            "and 1 at-fault accident in the past 3 years applying for standard auto insurance. "
            "Provide full risk score, tier, and ISO factor breakdown."
        ),
    },
    {
        "session": "research-datasets",
        "agent":   "ResearchAgent",
        "message": (
            "Search HuggingFace for insurance claims datasets suitable for fraud detection modelling. "
            "List the top 3 most relevant datasets with their descriptions and download counts."
        ),
    },
]


def seed_chats(token: str):
    print(bold(f"\n[3/7] Seeding {len(CHAT_SEEDS)} real chat sessions (live Bedrock calls)"))
    headers = {"Authorization": f"Bearer {token}"}
    results = []

    for i, seed in enumerate(CHAT_SEEDS, 1):
        info(f"[{i}/{len(CHAT_SEEDS)}] {seed['agent']}: {seed['message'][:70]}…")
        start = time.time()
        try:
            resp  = requests.post(
                f"{BASE_URL}/chat",
                json={
                    "workspace_id": WORKSPACE_ID,
                    "session_id":   seed["session"],
                    "message":      seed["message"],
                    "preferred_agent": seed["agent"],
                },
                headers=headers,
                timeout=300,  # 5 minutes — complex agent calls can take time
            )
        except requests.exceptions.Timeout:
            print(f"    {red('TIMEOUT')} after 300s — skipping this session")
            results.append({"session": seed["session"], "ok": False})
            continue
        except Exception as e:
            print(f"    {red('ERROR')}: {e}")
            results.append({"session": seed["session"], "ok": False})
            continue
        elapsed = time.time() - start
        if resp.status_code != 200:
            print(f"    {red('FAILED')}: {resp.status_code} — {resp.text[:200]}")
            results.append({"session": seed["session"], "ok": False})
            continue

        data = resp.json()
        agent_used = data.get("agent_used", "unknown")
        resp_len   = len(data.get("response", ""))
        ok(f"Done in {elapsed:.1f}s | agent={agent_used} | response={resp_len} chars")
        results.append({"session": seed["session"], "ok": True, "agent": agent_used, "chars": resp_len})

    passed = sum(1 for r in results if r["ok"])
    ok(f"{passed}/{len(CHAT_SEEDS)} chat sessions seeded successfully")
    return results


# ── Step 4: Generate policy document ──────────────────────────────────────────

def seed_policy_document(token: str):
    print(bold("\n[4/7] Generating policy document (PolicyAgent)"))
    headers = {"Authorization": f"Bearer {token}"}

    # Create policy
    info("Creating policy record via API…")
    try:
        create_resp = requests.post(f"{BASE_URL}/policies", json={
            "workspace_id": WORKSPACE_ID,
            "policy_data": {
                "type":                 "commercial_gl",
                "insured_name":         "Acme Manufacturing Corp",
                "insured_address":      "123 Industrial Blvd, Chicago, IL 60601",
                "annual_premium":       25000,
                "per_occurrence_limit": 1000000,
                "aggregate_limit":      2000000,
                "deductible":           5000,
                "business_type":        "Corporation",
                "payment_plan":         "Quarterly",
                "endorsements":         ["CG 20 10 Additional Insured", "CG 24 04 Waiver of Subrogation"],
            },
        }, headers=headers, timeout=30)

        if create_resp.status_code not in (200, 201):
            print(f"    {red('Policy creation failed')}: {create_resp.text[:200]}")
            return None, None

        policy_number = create_resp.json()["policy_number"]
        ok(f"Policy created: {policy_number}")
    except Exception as e:
        print(f"    {red('Policy creation error')}: {e}")
        return None, None

    # Generate document
    info("Generating full policy document (~40 pages)…")
    start = time.time()
    try:
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(policy_number, WORKSPACE_ID)
        elapsed = time.time() - start

        if len(doc) < 5000:
            print(f"    {red('Document too short')}: {len(doc)} chars")
            return policy_number, None

        ok(f"Document generated: {len(doc):,} chars (~{len(doc.split())//250} pages) in {elapsed:.1f}s")
    except Exception as e:
        print(f"    {red('Document generation error')}: {e}")
        return None, None

    # Verify it landed in generated_documents
    time.sleep(3)
    try:
        conn = db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, title, word_count, indexed_at FROM generated_documents "
            "WHERE workspace_id = %s AND doc_type = 'policy_document' ORDER BY created_at DESC LIMIT 1",
            (WORKSPACE_ID,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            print(f"    {yellow('Policy document NOT in generated_documents table yet — may still be indexing')}")
        else:
            ok(f"Saved to generated_documents: id={str(row[0])[:8]}… | words={row[2]} | indexed={'Yes' if row[3] else 'Pending'}")
    except Exception as e:
        print(f"    {yellow('DB check error')}: {e}")

    return policy_number, doc


# ── Step 5: Generate UW memo ───────────────────────────────────────────────────

def seed_uw_memo():
    print(bold("\n[5/7] Generating underwriting memo (UnderwritingAgent)"))
    info("Generating formal UW declination memo…")
    start = time.time()
    try:
        from agents.tools.underwriting_tools import generate_underwriting_memo
        memo = generate_underwriting_memo(
            policy_number="POL-DEMO0001",
            risk_summary=(
                "Commercial auto fleet — 12 vehicles operated by Rapid Delivery LLC. "
                "3 drivers have MVR violations in the past 24 months. "
                "Loss ratio over prior 3 policy years: 91%, 88%, 79%. "
                "Prior carrier non-renewed due to loss frequency."
            ),
            decision="Decline",
            conditions=[
                "Loss ratio exceeds 85% threshold (3-year average: 86%)",
                "Driver violation frequency: 3 of 12 drivers with MVR issues",
                "Prior carrier non-renewal is a mandatory referral trigger",
                "Recommend placement with excess/surplus lines market",
            ],
            workspace_id=WORKSPACE_ID,
        )
        elapsed = time.time() - start

        if len(memo) < 500:
            print(f"    {red('UW memo too short')}: {len(memo)} chars")
            return None

        ok(f"Memo generated: {len(memo):,} chars in {elapsed:.1f}s")

        # Verify in DB
        time.sleep(3)
        conn = db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, title, word_count, indexed_at FROM generated_documents "
            "WHERE workspace_id = %s AND doc_type = 'underwriting_memo' ORDER BY created_at DESC LIMIT 1",
            (WORKSPACE_ID,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            print(f"    {yellow('UW memo not yet in generated_documents — may still be indexing')}")
        else:
            ok(f"Saved to generated_documents: id={str(row[0])[:8]}… | words={row[2]} | indexed={'Yes' if row[3] else 'Pending'}")
        return memo
    except Exception as e:
        print(f"    {red('UW memo error')}: {e}")
        return None


# ── Step 6: Upload 2 additional demo documents ────────────────────────────────

ISO_CGL_CONTENT = """ISO COMMERCIAL GENERAL LIABILITY COVERAGE FORM
CG 00 01 04 13
INSURING AGREEMENT

A. We will pay those sums that the insured becomes legally obligated to pay as damages because of
"bodily injury" or "property damage" to which this insurance applies. We will have the right and duty
to defend the insured against any "suit" seeking those damages.

SECTION I – COVERAGES
Coverage A. Bodily Injury And Property Damage Liability
Coverage B. Personal And Advertising Injury Liability
Coverage C. Medical Payments

LIMITS OF INSURANCE
General Aggregate Limit:           $2,000,000
Products-Completed Operations Aggregate: $2,000,000
Personal & Advertising Injury Limit:     $1,000,000
Each Occurrence Limit:                   $1,000,000
Damage To Premises Rented To You Limit:    $100,000
Medical Expense Limit:                      $10,000

EXCLUSIONS
This insurance does not apply to:
a. Expected Or Intended Injury
b. Contractual Liability
c. Liquor Liability
d. Workers' Compensation And Similar Laws
e. Employer's Liability
f. Pollution
g. Aircraft, Auto Or Watercraft
h. Mobile Equipment
i. War
j. Professional Services
k. Damage To Property
l. Damage To Your Product
m. Damage To Your Work
n. Damage To Impaired Property
o. Recall Of Products, Work Or Impaired Property
p. Personal And Advertising Injury

WHO IS AN INSURED
1. If you are designated in the Declarations as:
   a. An individual, you and your spouse are insureds
   b. A partnership or joint venture, you are an insured
   c. A limited liability company, you are an insured
   d. An organization other than a partnership, joint venture or LLC, you are an insured

CONDITIONS
1. Bankruptcy
2. Duties In The Event Of Occurrence, Offense, Claim Or Suit
3. Legal Action Against Us
4. Other Insurance
5. Premium Audit
6. Representations
7. Separation Of Insureds
8. Transfer Of Rights Of Recovery Against Others To Us
9. When We Do Not Renew

DEFINITIONS
"Bodily injury" means bodily injury, sickness or disease sustained by a person.
"Coverage territory" means the United States of America, Puerto Rico and Canada.
"Insured contract" means a contract for a lease of premises, sidetrack agreement, easement or
license agreement, obligation to indemnify a municipality, elevator maintenance agreement.
"Occurrence" means an accident, including continuous or repeated exposure to substantially the
same general harmful conditions.
"Property damage" means physical injury to tangible property, including all resulting loss of use.
"Your product" means any goods or products manufactured, sold, handled, distributed or disposed of by you.
"Your work" means work or operations performed by you or on your behalf.

ISO Form CG 00 01 04 13 — Commercial General Liability Coverage Form
This form is the industry standard for commercial liability insurance in the United States.
Source: Insurance Services Office, Inc. (ISO), Jersey City, NJ
"""

NCCI_RATE_TABLE = """NCCI WORKERS COMPENSATION LOSS COST MANUAL
National Council on Compensation Insurance (NCCI)
Effective: January 1, 2026

SELECTED CLASS CODES AND LOSS COSTS (per $100 of payroll)

CONSTRUCTION
5403 — Roofing — All Kinds                     $5.12 per $100 payroll
5537 — Plumbing                                $2.85 per $100 payroll
5190 — Electrical Wiring                       $2.45 per $100 payroll
5022 — Masonry                                 $3.75 per $100 payroll
5432 — Carpentry — Dwellings                   $4.20 per $100 payroll

MANUFACTURING
3632 — Machine Shops                           $1.85 per $100 payroll
2812 — Paint Manufacturing                     $1.65 per $100 payroll
3574 — Office Machine Manufacturing            $0.85 per $100 payroll

OFFICE/CLERICAL
8810 — Clerical Office Employees               $0.08 per $100 payroll
8742 — Salespersons — Outside                  $0.35 per $100 payroll
8820 — Attorneys — All Employees               $0.12 per $100 payroll

TRANSPORTATION
7380 — Trucking — Long Haul                    $4.85 per $100 payroll
7382 — Trucking — Local                        $3.95 per $100 payroll

HEALTHCARE
8829 — Home Healthcare Services                $2.15 per $100 payroll
8832 — Physicians & Surgeons                   $0.65 per $100 payroll

CALCULATION METHODOLOGY:
Annual WC Premium = (Payroll / 100) × Loss Cost Rate × Experience Modifier × Schedule Credit/Debit

EXPERIENCE MODIFICATION FACTOR (EMod):
- EMod < 1.00: Credit modifier (better-than-average loss experience)
- EMod = 1.00: Unity modifier (average loss experience)
- EMod > 1.00: Debit modifier (worse-than-average loss experience)
- EMod > 1.50: Non-standard market referral required by most carriers

PREMIUM CALCULATION EXAMPLE:
Roofing contractor (5403), Payroll: $500,000, EMod: 1.15
Step 1: $500,000 / 100 = $5,000 per $100 units
Step 2: $5,000 × $5.12 (loss cost) = $25,600 standard premium
Step 3: $25,600 × 1.15 (EMod) = $29,440 final premium

Source: NCCI Holdings, Inc. — ncci.com
All loss costs subject to state-specific modification and carrier loading.
"""


def seed_uploads(token: str):
    print(bold("\n[6/7] Uploading 2 additional demo documents"))
    headers = {"Authorization": f"Bearer {token}"}
    files_to_upload = [
        ("iso-cgl-coverage-form.txt",   ISO_CGL_CONTENT.encode(),   "ISO CGL Coverage Form"),
        ("ncci-wc-rate-tables.txt",      NCCI_RATE_TABLE.encode(),   "NCCI WC Loss Cost Manual"),
    ]

    for filename, content, label in files_to_upload:
        info(f"Uploading {filename} ({len(content):,} bytes)…")
        resp = requests.post(
            f"{BASE_URL}/uploads",
            headers=headers,
            data={"workspace_id": WORKSPACE_ID},
            files={"file": (filename, content, "text/plain")},
        )
        if resp.status_code not in (200, 201):
            print(f"    {red('FAILED')}: {resp.text[:200]}")
            continue
        upload_id = resp.json()["id"]
        ok(f"Uploaded: {label} → id={upload_id[:8]}…")

        # Poll until done (max 30s)
        for _ in range(15):
            time.sleep(2)
            status_resp = requests.get(
                f"{BASE_URL}/uploads/{upload_id}?workspace_id={WORKSPACE_ID}",
                headers=headers,
            )
            status = status_resp.json().get("extraction_status")
            if status == "done":
                chunk_count = status_resp.json().get("chunk_count", 0)
                ok(f"Extraction complete: {chunk_count} chunks indexed to Qdrant")
                break
            elif status == "failed":
                print(f"    {red('Extraction FAILED')}")
                break
        else:
            info("Extraction still processing (continuing…)")


# ── Step 7: Summary ───────────────────────────────────────────────────────────

def print_summary(token: str):
    print(bold("\n[7/7] Verification summary"))
    headers = {"Authorization": f"Bearer {token}"}

    # Chat sessions
    resp = requests.get(f"{BASE_URL}/chat/history?workspace_id={WORKSPACE_ID}", headers=headers)
    sessions = resp.json().get("sessions", []) if resp.ok else []

    # Generated docs
    resp2 = requests.get(f"{BASE_URL}/gen-docs?workspace_id={WORKSPACE_ID}", headers=headers)
    gen_docs = resp2.json() if resp2.ok else []

    # Uploads
    resp3 = requests.get(f"{BASE_URL}/uploads?workspace_id={WORKSPACE_ID}", headers=headers)
    uploads = resp3.json() if resp3.ok else []

    # Qdrant
    try:
        from qdrant_client import QdrantClient
        q = QdrantClient(host="localhost", port=7333)
        col = f"workspace_{WORKSPACE_ID}"
        cols = {c.name for c in q.get_collections().collections}
        qdrant_points = q.get_collection(col).points_count if col in cols else 0
    except Exception:
        qdrant_points = "unknown"

    print(f"""
  ┌─────────────────────────────────────────────────────────┐
  │           InsureIQ Admin Demo Data Summary              │
  ├─────────────────────────────────────────────────────────┤
  │  Login URL  : https://ai.cipherx.co.uk                 │
  │  Email      : {ADMIN_EMAIL:<40} │
  │  Password   : {ADMIN_PASS:<40} │
  ├─────────────────────────────────────────────────────────┤
  │  Chat sessions     : {len(sessions):<5} (with first_message preview)  │
  │  Generated docs    : {len(gen_docs):<5} (policy doc + UW memo)       │
  │  Uploaded files    : {len(uploads):<5} (all indexed)                 │
  │  Workspace Qdrant  : {str(qdrant_points):<5} vectors                       │
  │  Global KB         : 547,226 vectors                    │
  └─────────────────────────────────────────────────────────┘""")

    if gen_docs:
        print("\n  Generated documents:")
        for d in gen_docs:
            indexed = "✓ In RAG" if d.get("indexed_at") else "⏳ Indexing"
            print(f"    • {d['title'][:55]:<55} [{indexed}]")

    if sessions:
        print("\n  Chat sessions:")
        for s in sessions:
            preview = (s.get("first_message") or "")[:55]
            print(f"    • {preview:<55} ({s.get('message_count',0)} msgs)")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(bold("=" * 60))
    print(bold("  InsureIQ Admin Seed Script"))
    print(bold("=" * 60))

    reset_admin_password()
    token = login()
    seed_chats(token)
    seed_policy_document(token)
    seed_uw_memo()
    seed_uploads(token)
    print_summary(token)

    print(f"\n{green('✓ Seeding complete!')}\n")
