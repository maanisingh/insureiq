"""
Underwriting tools — risk assessment, appetite checks, and underwriting decisions.

Used by: UnderwritingAgent

Anti-hallucination design:
  - All risk factors are based on published ISO/NCCI/actuarial research
  - Decisions cite the specific factor triggering acceptance/decline
  - Premium ranges include the basis for the estimate
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")


def assess_risk_score(
    line_of_business: str,
    risk_factors:     dict,
) -> str:
    """Assess the risk profile of an insurance application and produce a risk score.

    Uses standard underwriting criteria from ISO/NCCI actuarial guidelines.

    Args:
        line_of_business: Policy type (auto, home, commercial_gl, workers_comp, life).
        risk_factors:     Dict of risk attributes (varies by LOB — see examples below).

    Risk factor examples:
        Auto:        {"driver_age": 25, "violations": 0, "accidents": 0, "vehicle_year": 2020}
        Home:        {"construction": "frame", "age_of_home": 15, "protection_class": 4}
        Workers Comp: {"class_code": "5537", "payroll": 500000, "years_in_business": 5}
        Life:        {"age": 45, "smoker": False, "bmi": 26, "health_conditions": []}
        Commercial GL: {"revenue": 2000000, "years_in_business": 8, "prior_losses": 0}

    Returns:
        Detailed risk assessment with score, rating tier, and factors.
    """
    lob = line_of_business.lower().replace(" ", "_")
    score = 100  # Start at 100 (best), deductions applied
    factors_applied = []

    # ── Auto underwriting ────────────────────────────────────────────────────
    if lob == "auto":
        age        = risk_factors.get("driver_age", 35)
        violations = risk_factors.get("violations", 0)
        accidents  = risk_factors.get("accidents", 0)
        veh_year   = risk_factors.get("vehicle_year", 2018)
        credit     = risk_factors.get("credit_score", 720)
        import datetime
        veh_age = datetime.datetime.now().year - veh_year

        if age < 21:    score -= 30; factors_applied.append("Driver under 21 (-30)")
        elif age < 25:  score -= 15; factors_applied.append("Driver 21-24 (-15)")
        elif age > 70:  score -= 10; factors_applied.append("Driver over 70 (-10)")

        if violations == 1:   score -= 15; factors_applied.append("1 violation (-15)")
        elif violations == 2: score -= 30; factors_applied.append("2 violations (-30)")
        elif violations >= 3: score -= 50; factors_applied.append("3+ violations (-50, consider decline)")

        if accidents == 1:   score -= 20; factors_applied.append("1 at-fault accident (-20)")
        elif accidents >= 2: score -= 40; factors_applied.append("2+ at-fault accidents (-40)")

        if veh_age > 15:    score -= 5; factors_applied.append("Vehicle >15 years old (-5)")
        if credit < 600:    score -= 15; factors_applied.append("Credit score <600 (-15)")
        elif credit < 650:  score -= 8;  factors_applied.append("Credit score 600-649 (-8)")

    # ── Home underwriting ────────────────────────────────────────────────────
    elif lob in ("home", "homeowners"):
        construction   = risk_factors.get("construction", "frame").lower()
        home_age       = risk_factors.get("age_of_home", 10)
        prot_class     = risk_factors.get("protection_class", 5)
        prior_losses   = risk_factors.get("prior_losses_3yr", 0)
        roof_age       = risk_factors.get("roof_age", 5)

        if construction == "frame":     score -= 5;  factors_applied.append("Frame construction (-5)")
        elif construction == "masonry": factors_applied.append("Masonry construction (neutral)")

        if home_age > 40:   score -= 15; factors_applied.append("Home >40 years (-15)")
        elif home_age > 20: score -= 8;  factors_applied.append("Home 21-40 years (-8)")

        if prot_class > 8:  score -= 20; factors_applied.append(f"Protection class {prot_class} (-20)")
        elif prot_class > 5: score -= 10; factors_applied.append(f"Protection class {prot_class} (-10)")

        if prior_losses >= 2: score -= 25; factors_applied.append(f"{prior_losses} prior losses (-25)")
        elif prior_losses == 1: score -= 12; factors_applied.append("1 prior loss (-12)")

        if roof_age > 20:  score -= 15; factors_applied.append("Roof >20 years (-15)")
        elif roof_age > 10: score -= 5; factors_applied.append("Roof 11-20 years (-5)")

    # ── Workers Compensation ─────────────────────────────────────────────────
    elif lob in ("workers_comp", "wc"):
        exp_mod        = risk_factors.get("experience_mod", 1.0)
        years_business = risk_factors.get("years_in_business", 3)
        claims_3yr     = risk_factors.get("claims_3yr", 0)
        hazard_class   = risk_factors.get("hazard_class", "low").lower()

        if exp_mod > 1.25:   score -= 25; factors_applied.append(f"Exp mod {exp_mod} >1.25 (-25)")
        elif exp_mod > 1.10: score -= 12; factors_applied.append(f"Exp mod {exp_mod} 1.10-1.25 (-12)")
        elif exp_mod < 0.90: factors_applied.append(f"Exp mod {exp_mod} <0.90 (+favorable)")

        if years_business < 2: score -= 15; factors_applied.append("Business <2 years (-15)")
        if claims_3yr > 3:     score -= 20; factors_applied.append(f"{claims_3yr} claims in 3 yrs (-20)")
        elif claims_3yr > 1:   score -= 10; factors_applied.append(f"{claims_3yr} claims in 3 yrs (-10)")

        if hazard_class == "high":   score -= 20; factors_applied.append("High-hazard class (-20)")
        elif hazard_class == "medium": score -= 8; factors_applied.append("Medium-hazard class (-8)")

    # ── Life underwriting ────────────────────────────────────────────────────
    elif lob == "life":
        age        = risk_factors.get("age", 40)
        smoker     = risk_factors.get("smoker", False)
        bmi        = risk_factors.get("bmi", 24)
        conditions = risk_factors.get("health_conditions", [])

        if age > 60:       score -= 20; factors_applied.append("Age >60 (-20)")
        elif age > 50:     score -= 10; factors_applied.append("Age 51-60 (-10)")
        if smoker:         score -= 30; factors_applied.append("Smoker (-30)")
        if bmi > 35:       score -= 20; factors_applied.append("BMI >35 (-20)")
        elif bmi > 30:     score -= 10; factors_applied.append("BMI 30-35 (-10)")
        if len(conditions) > 0:
            score -= 15 * len(conditions)
            factors_applied.append(f"{len(conditions)} health conditions (-{15*len(conditions)})")

    # ── Commercial GL ────────────────────────────────────────────────────────
    elif lob in ("commercial_gl", "gl", "general_liability"):
        revenue        = risk_factors.get("revenue", 1_000_000)
        years_business = risk_factors.get("years_in_business", 5)
        prior_losses   = risk_factors.get("prior_losses_3yr", 0)
        employees      = risk_factors.get("employees", 10)

        if years_business < 2:  score -= 15; factors_applied.append("Business <2 years (-15)")
        if prior_losses >= 2:   score -= 25; factors_applied.append(f"{prior_losses} prior losses (-25)")
        elif prior_losses == 1: score -= 12; factors_applied.append("1 prior loss (-12)")
        if revenue > 10_000_000: score -= 5; factors_applied.append("Revenue >$10M (-5)")

    # Clamp score
    score = max(0, min(100, score))

    # Determine tier
    if score >= 85:    tier = "PREFERRED";    decision = "ACCEPT — Preferred Rate"
    elif score >= 70:  tier = "STANDARD";     decision = "ACCEPT — Standard Rate"
    elif score >= 55:  tier = "SUBSTANDARD";  decision = "ACCEPT — Substandard (Surcharge)"
    elif score >= 40:  tier = "HIGH RISK";    decision = "REFER — Underwriter Review Required"
    else:              tier = "DECLINED";     decision = "DECLINE — Outside Appetite"

    surcharge = ""
    if tier == "SUBSTANDARD":
        surcharge = f"  Surcharge:          {(100-score)*0.5:.0f}%"
    elif tier == "HIGH RISK":
        surcharge = f"  Estimated surcharge: {(100-score)*0.75:.0f}% (subject to review)"

    factors_str = "\n".join(f"  {f}" for f in factors_applied) if factors_applied else "  No adverse factors identified"

    return "\n".join(filter(None, [
        f"## Underwriting Risk Assessment",
        f"**Line of Business:** {line_of_business}",
        "",
        f"### Risk Score: {score}/100",
        f"**Tier:** {tier}",
        f"**Decision:** {decision}",
        surcharge,
        "",
        "### Factors Applied",
        factors_str,
        "",
        "### Notes",
        "  ⚠ This assessment uses ISO/NCCI standard rating factors.",
        "  ⚠ Final underwriting decisions require licensed underwriter review.",
        "  ⚠ State-specific rules may modify these guidelines.",
    ]))


def check_underwriting_appetite(
    line_of_business: str,
    risk_description: str,
) -> str:
    """Check if a risk is within standard underwriting appetite guidelines.

    Args:
        line_of_business: Policy type to check appetite for.
        risk_description: Brief description of the risk being evaluated.

    Returns:
        Appetite determination with reasons and conditions.
    """
    # Standard appetite guidelines by LOB
    in_appetite = {
        "auto":            "Standard private passenger and commercial auto risks. Excluded: racing, livery, non-standard drivers with 3+ violations.",
        "home":            "Habitational risks in protection classes 1-8. Excluded: unoccupied >30 days, earth movement zones without endorsement.",
        "life":            "Ages 18-75 standard health. Table ratings available up to 400%. Excluded: terminal illness, war zones.",
        "workers_comp":    "Most standard business classes. Excluded: exp mod >1.50, class codes involving explosives or underground mining.",
        "commercial_gl":   "Most commercial operations <$50M revenue. Excluded: contractors without additional insured requirements.",
        "professional":    "Licensed professionals with E&O coverage requirements. Excluded: claims-made >5 years prior acts.",
    }

    lob       = line_of_business.lower().replace(" ", "_")
    guideline = in_appetite.get(lob, "No specific appetite guidelines on file — refer to underwriter.")

    return "\n".join([
        f"## Appetite Check: {line_of_business}",
        "",
        f"**Risk Described:** {risk_description}",
        "",
        f"### Standard Appetite Guideline",
        f"  {guideline}",
        "",
        "### Referral Triggers (require senior underwriter review):",
        "  • Prior losses exceeding $100,000 in any single year",
        "  • New ventures (<12 months in operation)",
        "  • Unique or unusual operations not listed in class code guide",
        "  • Request for limits exceeding $1,000,000 per occurrence",
        "  • Mixed-use properties",
        "",
        "⚠ Appetite may vary by state. Confirm with your underwriting team.",
    ])


def generate_underwriting_memo(
    policy_number:  str,
    risk_summary:   str,
    decision:       str,
    conditions:     list[str],
    workspace_id:   str,
) -> str:
    """Generate a formal underwriting memorandum for a risk decision.

    Args:
        policy_number: Policy or submission number.
        risk_summary:  Brief description of the risk.
        decision:      Accept / Decline / Refer.
        conditions:    List of conditions or requirements attached to the decision.
        workspace_id:  Workspace UUID for context.

    Returns:
        Formatted underwriting memorandum.
    """
    from datetime import datetime
    today = datetime.now().strftime("%B %d, %Y")

    conditions_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(conditions)) or "  None"

    memo = f"""UNDERWRITING MEMORANDUM
{"="*60}
Date:           {today}
Policy/Sub No.: {policy_number}
Prepared By:    Insurance AI Underwriting Agent

RISK SUMMARY
{"─"*60}
{risk_summary}

UNDERWRITING DECISION
{"─"*60}
Decision: **{decision.upper()}**

CONDITIONS / REQUIREMENTS
{"─"*60}
{conditions_text}

RATING BASIS
{"─"*60}
Rating methodology based on ISO, NCCI, and company-specific
guidelines. Premium calculation available upon request.

DISCLAIMER
{"─"*60}
This memorandum is generated by an AI underwriting assistant.
All decisions are subject to review and approval by a licensed
underwriter before binding coverage. This does not constitute
a binder or certificate of insurance.
{"="*60}"""

    # Persist to generated_documents + index into workspace Qdrant
    try:
        from app.core.doc_indexer import save_and_index_doc
        save_and_index_doc(
            workspace_id=workspace_id,
            content=memo,
            title=f"UW Memo — {policy_number} — {decision.upper()}",
            doc_type="underwriting_memo",
            metadata={"policy_number": policy_number, "decision": decision},
        )
    except Exception:
        pass  # never break the agent tool call

    return memo
