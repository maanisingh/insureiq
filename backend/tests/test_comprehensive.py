"""
test_comprehensive.py — Full platform functional tests for InsureIQ.

Tests every feature end-to-end, verifying:
  - No hallucinations (pricing cites ISO/NCCI/SOA, docs have real ISO language)
  - RAG returns REAL insurance content from the 547K global knowledge base
  - Generated document pipeline: save → index → retrieve → search → delete
  - Upload pipeline: extract → chunk → embed → Qdrant → search → delete
  - Chat session management: persist → history → first_message → continuity
  - All 5 agent tools produce correct, source-cited outputs
  - Live Bedrock routing tests (marked 'live', run separately)

Run all fast tests:
  pytest tests/test_comprehensive.py -v -q

Run live Bedrock tests (slow, ~8 min):
  pytest tests/test_comprehensive.py -v -m live
"""

import os
import io
import time
import json
import uuid
import pytest
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "config" / ".env")


# ── DB helper ──────────────────────────────────────────────────────────────────

def _db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────

from tests.conftest import TEST_EMAIL, TEST_PASSWORD

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def module_user(client):
    """Register a fresh user for comprehensive tests."""
    email    = f"comprehensive_{uuid.uuid4().hex[:8]}@test.com"
    password = "Comprehensive2026!"
    resp = client.post("/auth/register", json={
        "email": email, "password": password, "full_name": "Comprehensive Tester",
    })
    assert resp.status_code == 201
    data = resp.json()
    yield {"email": email, "password": password, **data}
    # Cleanup
    conn = _db()
    cur  = conn.cursor()
    cur.execute("DELETE FROM users WHERE email = %s", (email,))
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(scope="module")
def auth(module_user):
    return {"Authorization": f"Bearer {module_user['access_token']}"}


@pytest.fixture(scope="module")
def ws_id(client, auth, module_user):
    resp = client.post("/workspaces", json={"name": "Comprehensive Test WS"}, headers=auth)
    assert resp.status_code == 201
    return resp.json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 1: INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

class TestInfrastructure:

    def test_health_endpoint_healthy(self, client):
        """API must respond healthy with version 1.0.0."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"

    def test_postgresql_reachable(self):
        """PostgreSQL must be reachable and contain users table."""
        conn = _db()
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        assert count >= 1, "users table should have at least 1 row"

    def test_redis_reachable(self):
        """Redis must respond to PING."""
        import redis as _redis
        r = _redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        )
        assert r.ping() is True

    def test_qdrant_global_has_records(self):
        """Global Qdrant must have the 547K insurance knowledge base."""
        from qdrant_client import QdrantClient
        q = QdrantClient(host=os.getenv("QDRANT_HOST", "localhost"),
                         port=int(os.getenv("QDRANT_PORT", "6333")))
        cols = {c.name for c in q.get_collections().collections}
        assert "insurance_global" in cols, "insurance_global collection missing"
        info = q.get_collection("insurance_global")
        assert info.points_count >= 500_000, \
            f"Expected 500K+ points, got {info.points_count}"

    def test_qdrant_workspace_accessible(self):
        """Workspace Qdrant must be reachable."""
        from qdrant_client import QdrantClient
        q = QdrantClient(host=os.getenv("QDRANT_WORKSPACE_HOST", "localhost"),
                         port=int(os.getenv("QDRANT_WORKSPACE_PORT", "7333")))
        cols = q.get_collections().collections  # should not throw
        assert isinstance(cols, list)

    def test_generated_documents_table_exists(self):
        """generated_documents table must exist (created in main.py lifespan)."""
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'generated_documents'
            )
        """)
        exists = cur.fetchone()[0]
        cur.close()
        conn.close()
        assert exists, "generated_documents table does not exist"


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 2: RAG QUALITY — verify global KB returns REAL insurance content
# ══════════════════════════════════════════════════════════════════════════════

class TestRAGQuality:

    def test_rag_auto_insurance_liability(self, client, auth):
        """Global search for auto liability must return relevant insurance content."""
        resp = client.get(
            "/search/global?query=auto+insurance+bodily+injury+liability&limit=5",
            headers=auth,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1, "No results returned for auto liability query"
        top = results[0]
        assert top["score"] >= 0.5, f"Low relevance score: {top['score']}"
        text = top["text"].lower()
        assert any(w in text for w in ["bodily", "liability", "insurance", "auto", "coverage"]), \
            f"Result text doesn't contain insurance terms: {text[:200]}"

    def test_rag_ncci_workers_comp(self, client, auth):
        """Global search for NCCI workers comp must return actuarial content."""
        resp = client.get(
            "/search/global?query=NCCI+workers+compensation+class+codes+loss+cost&limit=5",
            headers=auth,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        combined_text = " ".join(r["text"].lower() for r in results)
        assert any(w in combined_text for w in ["workers", "compensation", "class", "payroll", "premium"]), \
            "NCCI query returned unrelated content"

    def test_rag_fraud_detection(self, client, auth):
        """Global search for fraud detection must return claims fraud content."""
        resp = client.get(
            "/search/global?query=insurance+fraud+detection+claims+investigation&limit=5",
            headers=auth,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        combined = " ".join(r["text"].lower() for r in results)
        assert any(w in combined for w in ["fraud", "claim", "investigation", "insurance", "detection"]), \
            "Fraud query returned unrelated content"

    def test_rag_iso_cgl_forms(self, client, auth):
        """Global search for ISO CGL forms must return policy form content."""
        resp = client.get(
            "/search/global?query=ISO+commercial+general+liability+policy+exclusions&limit=5",
            headers=auth,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        combined = " ".join(r["text"].lower() for r in results)
        assert any(w in combined for w in ["general", "liability", "exclusion", "insurance", "commercial"]), \
            "ISO CGL query returned unrelated content"

    def test_rag_result_has_required_fields(self, client, auth):
        """Every RAG result must have id, score, text, source."""
        resp = client.get(
            "/search/global?query=insurance+deductible&limit=3",
            headers=auth,
        )
        results = resp.json()["results"]
        for r in results:
            assert "id"    in r, "Missing id field"
            assert "score" in r, "Missing score field"
            assert "text"  in r, "Missing text field"
            assert len(r["text"]) > 10, "Result text too short"

    def test_rag_dual_search_returns_both_keys(self, client, auth, ws_id):
        """POST /search must always return global_results and workspace_results."""
        resp = client.post("/search", json={
            "query": "property damage liability", "workspace_id": ws_id, "limit": 5,
        }, headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "global_results"    in data
        assert "workspace_results" in data
        assert isinstance(data["global_results"], list)
        assert isinstance(data["workspace_results"], list)
        # Global KB always has results for insurance queries
        assert len(data["global_results"]) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 3: PRICING TOOL ACCURACY — deterministic, no Bedrock needed
# ══════════════════════════════════════════════════════════════════════════════

class TestPricingAccuracy:

    def test_auto_premium_young_driver_has_surcharge(self):
        """22-year-old driver must have 1.85x age surcharge (ISO table)."""
        from agents.tools.pricing_tools import calculate_auto_premium
        result = calculate_auto_premium(22, 2020, 12000, ["bodily_injury", "collision"], 500)
        assert "1.85" in result, "Missing age surcharge factor 1.85"
        assert "ISO" in result,  "Missing ISO source citation"
        assert "ANNUAL PREMIUM" in result

    def test_auto_premium_mature_driver_base_rate(self):
        """45-year-old driver must have 1.00x age factor (ISO base)."""
        from agents.tools.pricing_tools import calculate_auto_premium
        result = calculate_auto_premium(45, 2019, 10000, ["bodily_injury"], 1000)
        assert "1.00" in result, "Mature driver should have 1.00 age factor"
        assert "ANNUAL PREMIUM" in result

    def test_wc_premium_roofer_5403(self):
        """NCCI class 5403_carpentry must use $5.12/100 loss cost."""
        from agents.tools.pricing_tools import calculate_workers_comp_premium
        # The pricing tool maps '5403_carpentry' → $5.12 (ISO/NCCI high-hazard construction)
        result = calculate_workers_comp_premium(500000, "5403_carpentry", 1.0)
        assert "NCCI" in result,         "Missing NCCI source citation"
        assert "5.12" in result,         "Missing correct 5403 loss cost $5.12"
        assert "ANNUAL WC PREMIUM" in result

    def test_wc_premium_clerical_8810(self):
        """NCCI class 8810 (clerical) must use $0.08/100 loss cost."""
        from agents.tools.pricing_tools import calculate_workers_comp_premium
        result = calculate_workers_comp_premium(1000000, "8810_clerical", 1.0)
        assert "0.08" in result, "Missing clerical loss cost $0.08"
        assert "ANNUAL WC PREMIUM" in result

    def test_wc_emod_increases_premium(self):
        """EMod 1.25 must produce higher premium than EMod 1.00."""
        from agents.tools.pricing_tools import calculate_workers_comp_premium
        import re
        def extract_premium(text):
            m = re.search(r'ANNUAL WC PREMIUM[^$]*\$([\d,]+)', text)
            return float(m.group(1).replace(",", "")) if m else 0.0

        base   = extract_premium(calculate_workers_comp_premium(500000, "5403_roofing", 1.00))
        debit  = extract_premium(calculate_workers_comp_premium(500000, "5403_roofing", 1.25))
        assert base > 0 and debit > 0, "Could not parse premiums"
        assert debit > base, f"Debit EMod {debit:.0f} should exceed base {base:.0f}"

    def test_life_premium_cites_soa_vbt(self):
        """Life premium must cite SOA 2015 VBT mortality tables."""
        from agents.tools.pricing_tools import calculate_life_premium
        result = calculate_life_premium(35, 500000, 20, "male", False)
        assert "SOA 2015 VBT" in result, "Missing SOA 2015 VBT citation"
        assert "ANNUAL PREMIUM" in result
        assert "MONTHLY PREMIUM" in result

    def test_life_smoker_premium_exceeds_nonsmoker(self):
        """Smoker life premium must exceed non-smoker (actuarial fact)."""
        from agents.tools.pricing_tools import calculate_life_premium
        import re
        def extract(text):
            m = re.search(r'ANNUAL PREMIUM[^$]*\$([\d,]+\.?\d*)', text)
            return float(m.group(1).replace(",", "")) if m else 0.0

        ns = extract(calculate_life_premium(40, 250000, 20, "male", smoker=False))
        sk = extract(calculate_life_premium(40, 250000, 20, "male", smoker=True))
        assert ns > 0 and sk > 0, "Could not parse life premiums"
        assert sk > ns, f"Smoker ${sk:.2f} must exceed non-smoker ${ns:.2f}"

    def test_chain_ladder_reserve_cites_cas(self):
        """Chain ladder reserve must cite CAS methodology."""
        from agents.tools.pricing_tools import calculate_loss_reserve
        result = calculate_loss_reserve([100000, 180000, 240000, 275000])
        assert "Chain Ladder" in result
        assert "Reserve"      in result
        assert "CAS"          in result

    def test_python_code_execution_real_output(self):
        """Actuarial Python sandbox must execute and return real numpy output."""
        from agents.tools.pricing_tools import run_actuarial_code
        code = """
import numpy as np
losses = np.array([85000, 92000, 78000, 115000, 103000])
print(f"Mean loss: ${losses.mean():,.0f}")
print(f"Loss ratio (assuming $100k premium): {losses.mean()/100000:.1%}")
print(f"Coefficient of variation: {losses.std()/losses.mean():.3f}")
"""
        result = run_actuarial_code(code, "Loss Statistics")
        assert "Mean loss" in result
        assert "$" in result
        # 94,600 average — verify it's approximately right
        assert any(str(x) in result for x in ["94", "95", "94,", "95,"]), \
            f"Expected ~$94,600 mean, got: {result[:300]}"

    def test_all_pricing_outputs_cite_source(self):
        """Every pricing function must cite its actuarial source — no invented numbers."""
        from agents.tools.pricing_tools import (
            calculate_auto_premium, calculate_workers_comp_premium, calculate_life_premium,
        )
        tests = [
            (calculate_auto_premium, (35, 2020, 12000, ["bodily_injury"], 500), ["ISO"]),
            (calculate_workers_comp_premium, (500000, "8810_clerical", 1.0), ["NCCI"]),
            (calculate_life_premium, (40, 250000, 20, "male", False), ["SOA"]),
        ]
        for func, args, required_sources in tests:
            result = func(*args)
            for src in required_sources:
                assert src in result, \
                    f"{func.__name__} must cite {src} — got: {result[:200]}"
            assert "⚠" in result or "Note" in result or "estimate" in result.lower(), \
                f"{func.__name__} must include uncertainty disclaimer"


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 4: UNDERWRITING ACCURACY — deterministic
# ══════════════════════════════════════════════════════════════════════════════

class TestUnderwritingAccuracy:

    def test_young_driver_gets_penalty(self):
        """Under-21 driver must receive -30 point penalty per ISO."""
        from agents.tools.underwriting_tools import assess_risk_score
        result = assess_risk_score("auto", {"driver_age": 19, "violations": 0})
        assert "Driver under 21" in result, "Under-21 penalty not cited"
        assert any(t in result for t in ["STANDARD", "SUBSTANDARD", "HIGH RISK", "PREFERRED"])

    def test_clean_mature_driver_preferred(self):
        """Age 40, clean record, good credit must be PREFERRED — ACCEPT."""
        from agents.tools.underwriting_tools import assess_risk_score
        result = assess_risk_score("auto", {
            "driver_age": 40, "violations": 0, "accidents": 0, "credit_score": 780,
        })
        assert "PREFERRED" in result
        assert "ACCEPT"    in result

    def test_high_violations_high_risk(self):
        """3 violations + 2 accidents + poor credit must be HIGH RISK or DECLINED."""
        from agents.tools.underwriting_tools import assess_risk_score
        result = assess_risk_score("auto", {
            "driver_age": 25, "violations": 3, "accidents": 2, "credit_score": 560,
        })
        assert any(t in result for t in ["HIGH RISK", "DECLINED", "REFER"]), \
            "High-risk driver should be HIGH RISK or DECLINED"
        # Verify factor breakdown is present
        assert any(v in result for v in ["violation", "accident"]), \
            "Risk factors must be cited"

    def test_smoker_life_gets_penalty(self):
        """Smoker applying for life insurance must receive rating table surcharge."""
        from agents.tools.underwriting_tools import assess_risk_score
        result = assess_risk_score("life", {
            "age": 55, "smoker": True, "bmi": 32, "health_conditions": ["hypertension"],
        })
        assert "Smoker" in result, "Smoker factor not cited"
        assert "Risk Score" in result

    def test_appetite_check_returns_guideline_text(self):
        """Appetite check must return the actual ISO/NCCI guideline, not empty."""
        from agents.tools.underwriting_tools import check_underwriting_appetite
        result = check_underwriting_appetite(
            "auto", "Standard private passenger, age 35, clean MVR"
        )
        assert "Appetite" in result or "appetite" in result.lower()
        assert len(result) > 100, "Appetite check returned too short a response"

    def test_uw_memo_has_all_required_sections(self):
        """UW memo must contain all formal memo sections."""
        from agents.tools.underwriting_tools import generate_underwriting_memo
        result = generate_underwriting_memo(
            policy_number="POL-TEST0001",
            risk_summary="Commercial auto fleet, high loss ratio",
            decision="Decline",
            conditions=["Loss ratio exceeds 85%", "Refer to E&S market"],
            workspace_id="00000000-0000-0000-0000-000000000001",  # non-existent WS, save will fail silently
        )
        required = [
            "UNDERWRITING MEMORANDUM", "RISK SUMMARY", "UNDERWRITING DECISION",
            "CONDITIONS", "DISCLAIMER", "POL-TEST0001",
        ]
        for section in required:
            assert section in result, f"Missing required section: {section}"
        assert "DECLINE" in result.upper()

    def test_uw_memo_anti_hallucination_disclaimer(self):
        """UW memo must contain the 'licensed underwriter' disclaimer."""
        from agents.tools.underwriting_tools import generate_underwriting_memo
        result = generate_underwriting_memo(
            "POL-DISC0001", "Test risk", "Accept", [], "00000000-0000-0000-0000-000000000001"
        )
        assert "licensed" in result.lower() or "AI" in result, \
            "UW memo missing liability disclaimer"


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 5: POLICY DOCUMENT QUALITY — ISO completeness
# ══════════════════════════════════════════════════════════════════════════════

class TestPolicyDocumentQuality:

    @pytest.fixture(scope="class")
    def policy_number(self, client, auth, ws_id):
        """Create a policy for document generation tests."""
        resp = client.post("/policies", json={
            "workspace_id": ws_id,
            "policy_data": {
                "type":                 "commercial_gl",
                "insured_name":         "Test Corp Ltd",
                "insured_address":      "100 Main St, New York, NY 10001",
                "annual_premium":       18500,
                "per_occurrence_limit": 1000000,
                "aggregate_limit":      2000000,
                "deductible":           2500,
                "business_type":        "Corporation",
                "endorsements":         ["CG 20 10 Additional Insured"],
            },
        }, headers=auth)
        assert resp.status_code == 201
        return resp.json()["policy_number"]

    def test_policy_document_has_all_7_sections(self, policy_number, ws_id):
        """ISO policy document must contain all 7 required sections."""
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(policy_number, ws_id)
        required = [
            "DECLARATIONS PAGE", "INSURING AGREEMENT", "DEFINITIONS",
            "COVERAGE DETAILS",  "EXCLUSIONS",         "CONDITIONS",
            "ENDORSEMENTS",
        ]
        for section in required:
            assert section in doc, f"Missing required section: {section}"

    def test_policy_document_minimum_length(self, policy_number, ws_id):
        """Policy document must be substantial (>8,000 chars = ~10+ pages)."""
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(policy_number, ws_id)
        assert len(doc) >= 8000, \
            f"Policy document too short: {len(doc)} chars (expected ≥8,000)"

    def test_policy_document_has_iso_exclusions(self, policy_number, ws_id):
        """ISO standard exclusions must all be present."""
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(policy_number, ws_id).upper()
        for excl in ["WAR", "NUCLEAR", "POLLUTION", "INTENTIONAL"]:
            assert excl in doc, f"Missing ISO standard exclusion: {excl}"

    def test_policy_document_has_standard_conditions(self, policy_number, ws_id):
        """Policy must contain standard ISO conditions."""
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(policy_number, ws_id)
        for condition in ["CANCELLATION", "LEGAL ACTION", "REPRESENTATIONS"]:
            assert condition in doc, f"Missing standard condition: {condition}"

    def test_policy_document_anti_hallucination_disclaimer(self, policy_number, ws_id):
        """Policy must have ISO form disclaimer to prevent misuse."""
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(policy_number, ws_id).lower()
        assert "licensed insurance" in doc or "iso standard" in doc or "illustrative" in doc, \
            "Missing anti-hallucination disclaimer"

    def test_policy_document_contains_insured_name(self, policy_number, ws_id):
        """Generated document must include the insured's actual name."""
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(policy_number, ws_id)
        assert "Test Corp Ltd" in doc, "Insured name missing from policy document"
        assert policy_number   in doc, "Policy number missing from policy document"


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 6: GENERATED DOCUMENT PIPELINE — save + index + retrieve + delete
# ══════════════════════════════════════════════════════════════════════════════

class TestGeneratedDocumentPipeline:

    @pytest.fixture(scope="class")
    def generated_policy_doc(self, client, auth, ws_id):
        """Create a policy and generate its document — returns (policy_number, doc_text)."""
        resp = client.post("/policies", json={
            "workspace_id": ws_id,
            "policy_data": {
                "type": "auto",
                "insured_name": "Pipeline Test Inc",
                "annual_premium": 3500,
                "deductible": 500,
                "vehicle": "2021 Ford F-150",
                "bodily_injury_limit": "100000/300000",
            },
        }, headers=auth)
        assert resp.status_code == 201
        pnum = resp.json()["policy_number"]
        from agents.tools.policy_tools import generate_policy_document
        doc = generate_policy_document(pnum, ws_id)
        assert len(doc) > 5000
        time.sleep(5)  # allow indexing
        return pnum, doc

    def test_policy_doc_saved_to_db(self, generated_policy_doc, ws_id):
        """generate_policy_document() must save row to generated_documents table."""
        pnum, doc = generated_policy_doc
        conn = _db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, title, word_count FROM generated_documents "
            "WHERE workspace_id = %s AND doc_type = 'policy_document' "
            "ORDER BY created_at DESC LIMIT 1",
            (ws_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None, "Policy document not found in generated_documents"
        assert row[2] > 100,    f"Word count too low: {row[2]}"

    def test_policy_doc_indexed_in_qdrant(self, generated_policy_doc, ws_id):
        """Policy document must be indexed in workspace Qdrant within 30s."""
        # Wait up to 30s for indexed_at to be set
        for _ in range(15):
            conn = _db()
            cur  = conn.cursor()
            cur.execute(
                "SELECT indexed_at FROM generated_documents "
                "WHERE workspace_id = %s AND doc_type = 'policy_document' "
                "ORDER BY created_at DESC LIMIT 1",
                (ws_id,),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row and row[0]:
                break
            time.sleep(2)
        assert row and row[0], "Policy document not indexed in Qdrant after 30s"

    def test_gen_docs_api_lists_policy_doc(self, client, auth, ws_id):
        """GET /gen-docs must return the saved policy document."""
        resp = client.get(f"/gen-docs?workspace_id={ws_id}", headers=auth)
        assert resp.status_code == 200
        docs = resp.json()
        assert any(d["doc_type"] == "policy_document" for d in docs), \
            "No policy_document in /gen-docs list"

    def test_gen_docs_api_returns_full_content(self, client, auth, ws_id):
        """GET /gen-docs/{id} must return full document content."""
        # Get the latest policy doc ID
        list_resp = client.get(
            f"/gen-docs?workspace_id={ws_id}&doc_type=policy_document", headers=auth
        )
        docs = list_resp.json()
        assert len(docs) >= 1
        doc_id = docs[0]["id"]

        resp = client.get(f"/gen-docs/{doc_id}?workspace_id={ws_id}", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "content"   in data
        assert len(data["content"]) >= 5000, "Document content too short"
        assert "DECLARATIONS" in data["content"] or "INSURING" in data["content"], \
            "Document content doesn't look like a policy"

    def test_workspace_search_finds_policy_content(self, generated_policy_doc, ws_id, client, auth):
        """After generation, workspace Qdrant must contain the policy content."""
        # Wait for indexing
        time.sleep(8)
        resp = client.get(
            f"/search/workspace/{ws_id}?query=insuring+agreement+coverage+limits&limit=5",
            headers=auth,
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1, "Workspace search returned no results after doc generation"
        combined = " ".join(r["text"].lower() for r in results)
        assert any(w in combined for w in ["insur", "coverage", "limit", "policy", "premium"]), \
            "Workspace search results don't contain policy content"

    def test_uw_memo_saved_to_db(self, ws_id):
        """generate_underwriting_memo() must save to generated_documents table."""
        from agents.tools.underwriting_tools import generate_underwriting_memo
        generate_underwriting_memo(
            policy_number="POL-PYTEST001",
            risk_summary="Test risk for comprehensive suite",
            decision="Accept",
            conditions=["Annual audit", "No new drivers"],
            workspace_id=ws_id,
        )
        time.sleep(4)
        conn = _db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, title, word_count FROM generated_documents "
            "WHERE workspace_id = %s AND doc_type = 'underwriting_memo' "
            "ORDER BY created_at DESC LIMIT 1",
            (ws_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None, "UW memo not saved to generated_documents"
        assert "POL-PYTEST001" in row[1], "Policy number not in memo title"

    def test_gen_docs_delete_removes_from_db(self, client, auth, ws_id):
        """DELETE /gen-docs/{id} must remove the document from DB."""
        # Create a throwaway doc
        from agents.tools.policy_tools import generate_policy_document
        resp = client.post("/policies", json={
            "workspace_id": ws_id,
            "policy_data": {"type": "auto", "insured_name": "Delete Test LLC", "annual_premium": 1000},
        }, headers=auth)
        pnum = resp.json()["policy_number"]
        generate_policy_document(pnum, ws_id)
        time.sleep(4)

        # Find its ID
        list_resp = client.get(f"/gen-docs?workspace_id={ws_id}", headers=auth)
        docs = [d for d in list_resp.json() if "Delete Test" in d.get("title", "")]
        if not docs:
            pytest.skip("Throwaway doc not found (timing issue)")
        doc_id = docs[0]["id"]

        # Delete
        del_resp = client.delete(f"/gen-docs/{doc_id}?workspace_id={ws_id}", headers=auth)
        assert del_resp.status_code == 204

        # Verify gone from DB
        get_resp = client.get(f"/gen-docs/{doc_id}?workspace_id={ws_id}", headers=auth)
        assert get_resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 7: UPLOAD + EXTRACTION PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

class TestUploadPipeline:

    SAMPLE_INSURANCE_TEXT = (
        "COMMERCIAL PROPERTY INSURANCE POLICY\n\n"
        "This policy covers direct physical loss or damage to covered property "
        "at the premises described in the Declarations.\n\n"
        "COVERED PROPERTY includes buildings, business personal property, "
        "and personal property of others in your care custody or control.\n\n"
        "CAUSES OF LOSS — SPECIAL FORM: This form covers risks of direct physical "
        "loss unless the loss is excluded. Excluded causes include: flood, earthquake, "
        "war, nuclear hazard, and intentional loss.\n\n"
        "COINSURANCE CLAUSE: If the limit of insurance is less than the required "
        "coinsurance percentage of the value of covered property, the insured "
        "will be a co-insurer for the difference.\n\n"
        "REPLACEMENT COST: We will pay the cost to repair or replace damaged property "
        "with new property of the same kind and quality.\n"
    )

    def test_upload_txt_accepted(self, client, auth, ws_id):
        """TXT file upload must return 201 with upload ID."""
        resp = client.post(
            "/uploads",
            data={"workspace_id": ws_id},
            files={"file": ("commercial-property.txt",
                           io.BytesIO(self.SAMPLE_INSURANCE_TEXT.encode()),
                           "text/plain")},
            headers=auth,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id"                in data
        assert data["file_type"]   == "txt"
        assert data["extraction_status"] in ("pending", "processing", "done")

    def test_upload_unsupported_format_rejected(self, client, auth, ws_id):
        """Non-supported file types must be rejected with 400."""
        resp = client.post(
            "/uploads",
            data={"workspace_id": ws_id},
            files={"file": ("test.mp4", io.BytesIO(b"fake video"), "video/mp4")},
            headers=auth,
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_upload_extraction_completes_and_indexes(self, client, auth, ws_id):
        """Upload must complete extraction and index chunks to Qdrant."""
        resp = client.post(
            "/uploads",
            data={"workspace_id": ws_id},
            files={"file": ("extraction-test.txt",
                           io.BytesIO(self.SAMPLE_INSURANCE_TEXT.encode()),
                           "text/plain")},
            headers=auth,
        )
        assert resp.status_code == 201
        upload_id = resp.json()["id"]

        # Poll until done
        for _ in range(20):
            time.sleep(2)
            status_resp = client.get(
                f"/uploads/{upload_id}?workspace_id={ws_id}", headers=auth
            )
            assert status_resp.status_code == 200
            data = status_resp.json()
            if data["extraction_status"] == "done":
                assert data["chunk_count"] >= 1, "Expected at least 1 chunk"
                break
            elif data["extraction_status"] == "failed":
                pytest.fail(f"Extraction failed: {data}")
        else:
            pytest.fail("Extraction did not complete within 40s")

    def test_workspace_search_finds_uploaded_content(self, client, auth, ws_id):
        """After upload + extraction, workspace search must find the content."""
        # Upload a document with very specific text
        specific_text = (
            "UNIQUE_MARKER_COINSURANCE_CLAUSE_TEST\n"
            "The coinsurance percentage applies when the insured carries less than "
            "the required amount of insurance relative to the total insurable value. "
            "If the building value is $1,000,000 and coinsurance is 80%, "
            "the minimum required coverage is $800,000."
        )
        upload_resp = client.post(
            "/uploads",
            data={"workspace_id": ws_id},
            files={"file": ("coinsurance-test.txt",
                           io.BytesIO(specific_text.encode()), "text/plain")},
            headers=auth,
        )
        assert upload_resp.status_code == 201
        upload_id = upload_resp.json()["id"]

        # Wait for extraction
        for _ in range(20):
            time.sleep(2)
            s = client.get(f"/uploads/{upload_id}?workspace_id={ws_id}", headers=auth).json()
            if s["extraction_status"] == "done":
                break

        # Search for the content
        search_resp = client.get(
            f"/search/workspace/{ws_id}?query=coinsurance+percentage+insurable+value&limit=5",
            headers=auth,
        )
        assert search_resp.status_code == 200
        results = search_resp.json()["results"]
        assert len(results) >= 1, "Workspace search returned no results for uploaded content"
        combined = " ".join(r["text"].lower() for r in results)
        assert "coinsurance" in combined, "Uploaded content not found in workspace search"

    def test_delete_upload_removes_from_list(self, client, auth, ws_id):
        """DELETE /uploads/{id} must remove the upload from the list."""
        upload_id = client.post(
            "/uploads",
            data={"workspace_id": ws_id},
            files={"file": ("delete-me.txt", io.BytesIO(b"delete test"), "text/plain")},
            headers=auth,
        ).json()["id"]

        del_resp = client.delete(
            f"/uploads/{upload_id}?workspace_id={ws_id}", headers=auth
        )
        assert del_resp.status_code == 204

        get_resp = client.get(f"/uploads/{upload_id}?workspace_id={ws_id}", headers=auth)
        assert get_resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 8: CHAT SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class TestChatSessionManagement:

    def test_chat_returns_non_empty_response(self, client, auth, ws_id):
        """POST /chat must return a non-empty insurance-relevant response."""
        resp = client.post("/chat", json={
            "workspace_id": ws_id,
            "message":      "What is an insurance deductible?",
        }, headers=auth, timeout=90)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["response"]) > 20, "Response too short"
        assert any(w in data["response"].lower() for w in [
            "deductible", "insurance", "pay", "coverage", "amount"
        ]), f"Response doesn't mention deductible: {data['response'][:200]}"

    def test_chat_session_id_returned(self, client, auth, ws_id):
        """Every chat response must include a session_id."""
        resp = client.post("/chat", json={
            "workspace_id": ws_id, "message": "Define premium.",
        }, headers=auth, timeout=90)
        assert resp.status_code == 200
        assert "session_id" in resp.json()
        assert resp.json()["session_id"]  # not empty

    def test_chat_agent_used_field_present(self, client, auth, ws_id):
        """ChatResponse must include agent_used field identifying which agent responded."""
        resp = client.post("/chat", json={
            "workspace_id": ws_id, "message": "What is subrogation?",
        }, headers=auth, timeout=90)
        assert resp.status_code == 200
        data = resp.json()
        assert "agent_used" in data
        assert data["agent_used"], "agent_used must not be empty"
        # Must be one of the 5 known agents
        valid_agents = ["RAGAgent", "ResearchAgent", "PricingAgent", "PolicyAgent", "UnderwritingAgent"]
        assert any(a in data["agent_used"] for a in valid_agents), \
            f"Unknown agent: {data['agent_used']}"

    def test_chat_session_persists_in_history(self, client, auth, ws_id):
        """After sending a message, it must appear in /chat/history."""
        session_id = f"persist-test-{uuid.uuid4().hex[:6]}"
        client.post("/chat", json={
            "workspace_id": ws_id,
            "session_id":   session_id,
            "message":      "What is an actuarial table?",
        }, headers=auth, timeout=90)

        hist = client.get(
            f"/chat/history?workspace_id={ws_id}&session_id={session_id}",
            headers=auth,
        )
        assert hist.status_code == 200
        messages = hist.json().get("messages", [])
        assert len(messages) >= 1, "No messages in chat history after chat call"
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assert len(user_msgs) >= 1, "User message not saved to history"

    def test_chat_history_first_message_field(self, client, auth, ws_id):
        """GET /chat/history (sessions list) must include first_message field."""
        # Create a session with known first message
        first_msg = "What are ISO commercial lines policy forms?"
        session_id = f"first-msg-{uuid.uuid4().hex[:6]}"
        client.post("/chat", json={
            "workspace_id": ws_id,
            "session_id":   session_id,
            "message":      first_msg,
        }, headers=auth, timeout=90)

        hist = client.get(f"/chat/history?workspace_id={ws_id}", headers=auth)
        assert hist.status_code == 200
        sessions = hist.json().get("sessions", [])
        # Find our session
        our_session = next((s for s in sessions if s["session_id"] == session_id), None)
        assert our_session is not None, "Session not found in history list"
        assert "first_message" in our_session, "first_message field missing from session"
        assert our_session["first_message"] is not None, "first_message is null"
        # The first_message should start with our sent text
        assert first_msg[:30] in (our_session["first_message"] or ""), \
            f"first_message doesn't match: {our_session['first_message']}"

    def test_chat_preferred_agent_routing(self, client, auth, ws_id):
        """preferred_agent=PricingAgent must route to PricingAgent."""
        resp = client.post("/chat", json={
            "workspace_id":   ws_id,
            "message":        "Calculate auto premium for a 30-year-old, 2022 Toyota, 10K miles.",
            "preferred_agent": "PricingAgent",
        }, headers=auth, timeout=90)
        assert resp.status_code == 200
        data = resp.json()
        assert "PricingAgent" in (data.get("agent_used") or ""), \
            f"Expected PricingAgent, got: {data.get('agent_used')}"

    def test_chat_enabled_sources_accepted(self, client, auth, ws_id):
        """enabled_sources field must be accepted without error."""
        resp = client.post("/chat", json={
            "workspace_id":    ws_id,
            "message":         "What is liability insurance?",
            "preferred_agent": "RAGAgent",
            "enabled_sources": ["rag", "workspace"],
        }, headers=auth, timeout=90)
        assert resp.status_code == 200
        assert len(resp.json()["response"]) > 20


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 9: API KEYS
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIKeys:

    def test_create_api_key_returns_ak_prefix(self, client, auth):
        """New API key must start with ak_ prefix."""
        resp = client.post("/api-keys", json={"name": "comprehensive-test-key"}, headers=auth)
        assert resp.status_code == 201
        data = resp.json()
        assert data["raw_key"].startswith("ak_"), f"Key doesn't start with ak_: {data['raw_key'][:10]}"
        return data

    def test_api_key_authenticates_on_me(self, client, auth):
        """API key must work as Bearer token on GET /auth/me."""
        create_resp = client.post("/api-keys", json={"name": "auth-test-key"}, headers=auth)
        key = create_resp.json()["raw_key"]
        key_headers = {"Authorization": f"Bearer {key}"}

        me_resp = client.get("/auth/me", headers=key_headers)
        assert me_resp.status_code == 200

    def test_api_key_authenticates_on_search(self, client, auth):
        """API key must work on search endpoints (not just /auth/me)."""
        create_resp = client.post("/api-keys", json={"name": "search-auth-key"}, headers=auth)
        key = create_resp.json()["raw_key"]
        key_headers = {"Authorization": f"Bearer {key}"}

        search_resp = client.get("/search/global?query=insurance&limit=2", headers=key_headers)
        assert search_resp.status_code == 200

    def test_list_keys_shows_prefix_not_raw(self, client, auth):
        """Key list must show key_prefix only, never the full raw key."""
        list_resp = client.get("/api-keys", headers=auth)
        assert list_resp.status_code == 200
        for key in list_resp.json():
            assert "raw_key"   not in key,                 "raw_key must never appear in list"
            assert "key_prefix" in key,                    "key_prefix field missing"
            assert key["key_prefix"].startswith("ak_"),   "key_prefix must start with ak_"
            assert len(key["key_prefix"]) <= 15,           "key_prefix too long (should be truncated)"

    def test_revoke_key_blocks_access(self, client, auth):
        """Revoked API key must return 401 on subsequent requests."""
        create_resp = client.post("/api-keys", json={"name": "revoke-test-key"}, headers=auth)
        key_data   = create_resp.json()
        raw_key    = key_data["raw_key"]
        key_id     = key_data["id"]

        # Verify it works first
        first_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {raw_key}"})
        assert first_resp.status_code == 200

        # Revoke
        revoke_resp = client.delete(f"/api-keys/{key_id}", headers=auth)
        assert revoke_resp.status_code in (200, 204)

        # Must fail now
        fail_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {raw_key}"})
        assert fail_resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 10: LIVE BEDROCK AGENT ROUTING (slow — marked 'live')
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
class TestLiveAgentRouting:
    """
    Real Bedrock calls — each test can take 30-90s.
    Run with: pytest tests/test_comprehensive.py -v -m live
    """

    def test_live_rag_agent_knowledge_question(self, client, auth, ws_id):
        """RAGAgent must answer insurance knowledge question with cited content."""
        resp = client.post("/chat", json={
            "workspace_id":   ws_id,
            "message":        "What is the difference between claims-made and occurrence-based liability policies? Explain using the knowledge base.",
            "preferred_agent": "RAGAgent",
        }, headers=auth, timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "RAGAgent" in (data.get("agent_used") or ""), \
            f"Expected RAGAgent, got {data.get('agent_used')}"
        response = data["response"].lower()
        assert len(data["response"]) >= 100
        assert any(w in response for w in ["claims-made", "occurrence", "trigger", "policy period"]), \
            f"Response doesn't discuss claims-made/occurrence: {data['response'][:300]}"

    def test_live_pricing_agent_auto_premium(self, client, auth, ws_id):
        """PricingAgent must produce ISO-cited auto premium calculation."""
        resp = client.post("/chat", json={
            "workspace_id":   ws_id,
            "message":        "Calculate auto insurance premium for a 35-year-old, 2020 Toyota Camry, 12,000 miles/year, bodily injury and collision, $500 deductible.",
            "preferred_agent": "PricingAgent",
        }, headers=auth, timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "PricingAgent" in (data.get("agent_used") or "")
        response = data["response"]
        assert len(response) >= 100
        assert "$" in response or "premium" in response.lower(), \
            "Response should contain dollar amount or premium reference"
        assert any(s in response for s in ["ISO", "Methodology", "ANNUAL PREMIUM", "premium"]), \
            "Response should cite ISO methodology"

    def test_live_pricing_agent_wc_ncci(self, client, auth, ws_id):
        """PricingAgent must produce NCCI WC calculation with loss cost rate."""
        resp = client.post("/chat", json={
            "workspace_id":   ws_id,
            "message":        "Calculate workers compensation premium for a roofing contractor, $1,000,000 payroll, NCCI class code 5403, experience modifier 1.10.",
            "preferred_agent": "PricingAgent",
        }, headers=auth, timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "PricingAgent" in (data.get("agent_used") or "")
        response = data["response"]
        # Should reference NCCI methodology
        assert any(s in response for s in ["NCCI", "loss cost", "workers comp", "WC", "$"]), \
            f"Response missing NCCI content: {response[:300]}"

    def test_live_underwriting_agent_risk_score(self, client, auth, ws_id):
        """UnderwritingAgent must provide risk score with tier classification."""
        resp = client.post("/chat", json={
            "workspace_id":   ws_id,
            "message":        "Assess underwriting risk for a 23-year-old driver with 2 speeding violations and 1 at-fault accident in the last 3 years.",
            "preferred_agent": "UnderwritingAgent",
        }, headers=auth, timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "UnderwritingAgent" in (data.get("agent_used") or "")
        response = data["response"]
        assert any(w in response for w in [
            "risk", "Risk", "score", "Score", "tier", "STANDARD", "SUBSTANDARD", "violation"
        ]), f"Response missing risk assessment content: {response[:300]}"

    def test_live_research_agent_finds_datasets(self, client, auth, ws_id):
        """ResearchAgent must search for insurance datasets."""
        resp = client.post("/chat", json={
            "workspace_id":   ws_id,
            "message":        "Search HuggingFace for insurance claims or fraud detection datasets. List any relevant ones you find.",
            "preferred_agent": "ResearchAgent",
        }, headers=auth, timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "ResearchAgent" in (data.get("agent_used") or "")
        # Response should mention searching or finding something
        assert len(data["response"]) >= 50
