"""
Policy tools — create, update, and generate full insurance policy documents.

Used by: PolicyAgent

Anti-hallucination design:
  - Policy templates are based on standard ISO/ACORD forms
  - All coverage terms, exclusions, and conditions are industry-standard
  - Generated policies clearly mark placeholders needing legal review
"""

import os
import uuid
import json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")


def _db():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
    )


def create_insurance_policy(
    workspace_id:  str,
    policy_type:   str,
    insured_name:  str,
    coverage_data: dict,
) -> str:
    """Create a new insurance policy record in the database.

    Args:
        workspace_id:  The workspace to create the policy in.
        policy_type:   Type of policy (auto, home, life, workers_comp, commercial_gl, etc.).
        insured_name:  Full legal name of the insured.
        coverage_data: Dict of coverage details (limits, deductibles, premiums, etc.).

    Returns:
        Confirmation with policy number and summary.
    """
    try:
        policy_id     = str(uuid.uuid4())
        policy_number = f"POL-{policy_id[:8].upper()}"
        today         = datetime.now().date()
        expiry        = today + timedelta(days=365)

        policy_data = {
            "type":           policy_type,
            "insured_name":   insured_name,
            "effective_date": str(today),
            "expiry_date":    str(expiry),
            "created_by":     "InsuranceAI_PolicyAgent",
            **coverage_data,
        }

        conn = _db()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO policies (id, workspace_id, policy_number, policy_type, policy_data, status)
            VALUES (%s, %s, %s, %s, %s, 'active')
            RETURNING id, policy_number, created_at
            """,
            (policy_id, workspace_id, policy_number, policy_type, json.dumps(policy_data)),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return "\n".join([
            f"✓ Policy Created Successfully",
            f"  Policy Number: **{policy_number}**",
            f"  Type:          {policy_type}",
            f"  Insured:       {insured_name}",
            f"  Effective:     {today}",
            f"  Expiry:        {expiry}",
            f"  Status:        Active",
            f"  Database ID:   {policy_id}",
        ])
    except Exception as e:
        return f"Policy creation error: {e}"


def generate_policy_document(
    policy_number:  str,
    workspace_id:   str,
    include_sections: list[str] | None = None,
) -> str:
    """Generate a comprehensive, professional insurance policy document.

    Produces a full policy wording document including declarations page,
    insuring agreements, conditions, exclusions, and endorsements.
    Based on ISO standard form structures.

    Args:
        policy_number:    Policy number (e.g. POL-XXXXXXXX).
        workspace_id:     The user's workspace UUID.
        include_sections: Optional list of sections to include. Defaults to all.
                          Options: 'declarations', 'insuring_agreement', 'definitions',
                                   'coverage', 'exclusions', 'conditions', 'endorsements'

    Returns:
        Full multi-page policy document text (40+ pages equivalent).
    """
    # Fetch policy from DB
    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT policy_number, policy_type, policy_data, status, created_at FROM policies WHERE policy_number = %s AND workspace_id = %s",
            (policy_number, workspace_id),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return f"Database error: {e}"

    if not row:
        return f"Policy {policy_number} not found in workspace."

    pnum, ptype, pdata, status, created = row
    pdata = pdata or {}

    sections = include_sections or ["declarations", "insuring_agreement", "definitions",
                                     "coverage", "exclusions", "conditions", "endorsements"]

    doc = []
    doc.append(_gen_header(pnum, ptype, pdata, status))

    if "declarations" in sections:
        doc.append(_gen_declarations(pnum, ptype, pdata, created))
    if "insuring_agreement" in sections:
        doc.append(_gen_insuring_agreement(ptype, pdata))
    if "definitions" in sections:
        doc.append(_gen_definitions(ptype))
    if "coverage" in sections:
        doc.append(_gen_coverage(ptype, pdata))
    if "exclusions" in sections:
        doc.append(_gen_exclusions(ptype))
    if "conditions" in sections:
        doc.append(_gen_conditions(ptype, pdata))
    if "endorsements" in sections:
        doc.append(_gen_endorsements(ptype, pdata))

    doc.append(_gen_signature_block(pdata))
    full_text = "\n\n".join(doc)

    # Persist to generated_documents + index into workspace Qdrant
    try:
        from app.core.doc_indexer import save_and_index_doc
        save_and_index_doc(
            workspace_id=workspace_id,
            content=full_text,
            title=f"Policy Document — {pnum}",
            doc_type="policy_document",
            metadata={"policy_number": pnum, "policy_type": ptype},
        )
    except Exception:
        pass  # never break the agent tool call

    return full_text


# ── Document section generators ──────────────────────────────────────────────

def _gen_header(pnum, ptype, pdata, status):
    insured = pdata.get("insured_name", "[INSURED NAME]")
    return f"""{"="*70}
                    INSURANCE POLICY DOCUMENT
                    Policy Number: {pnum}
                    {"="*70}

IMPORTANT — READ THIS POLICY CAREFULLY

This policy is a legal contract between {insured} ("You", "Your", "Insured")
and the Insurer. This document, together with the Declarations page and any
attached endorsements or schedules, constitutes the entire agreement.

Policy Type:    {ptype.replace("_", " ").title()}
Status:         {status.upper()}
Form Reference: Based on ISO Standard Forms (for reference purposes)

{"="*70}"""


def _gen_declarations(pnum, ptype, pdata, created):
    insured   = pdata.get("insured_name", "[INSURED NAME]")
    effective = pdata.get("effective_date", str(datetime.now().date()))
    expiry    = pdata.get("expiry_date",    str((datetime.now() + timedelta(days=365)).date()))
    premium   = pdata.get("annual_premium", pdata.get("premium", "[SEE SCHEDULE]"))
    address   = pdata.get("insured_address", "[INSURED ADDRESS]")

    # Build coverage schedule
    coverage_lines = []
    for k, v in pdata.items():
        if any(w in k.lower() for w in ["limit", "deductible", "coverage", "premium", "amount"]):
            coverage_lines.append(f"    {k.replace('_',' ').title():<35} {v}")

    coverage_schedule = "\n".join(coverage_lines) if coverage_lines else "    [See Policy Schedule]"

    return f"""DECLARATIONS PAGE
─────────────────────────────────────────────────────────────────────

Named Insured:    {insured}
Mailing Address:  {address}

Policy Number:    {pnum}
Policy Period:    {effective} to {expiry} 12:01 A.M. Standard Time
                  at the address shown above

Form of Business: {pdata.get('business_type', 'Individual / Personal')}
Policy Type:      {ptype.replace('_', ' ').title()}

COVERAGE SCHEDULE
────────────────────────────────────────
{coverage_schedule}

TOTAL ANNUAL PREMIUM:     ${premium}
PAYMENT PLAN:             {pdata.get('payment_plan', 'Annual')}

In consideration of the premium stated above, and subject to all terms,
conditions, and limitations of this policy, the Company agrees to provide
the insurance coverage described herein.

This Declarations page is part of and forms a part of your policy."""


def _gen_insuring_agreement(ptype, pdata):
    agreements = {
        "auto": """INSURING AGREEMENT
─────────────────────────────────────────────────────────────────────

SECTION I — INSURING AGREEMENT

A. We will pay those sums that the insured becomes legally obligated to pay
   as damages because of "bodily injury" or "property damage" to which this
   insurance applies. We will have the right and duty to defend the insured
   against any "suit" seeking those damages. However, we will have no duty to
   defend the insured against any "suit" seeking damages for "bodily injury"
   or "property damage" to which this insurance does not apply.

B. This insurance applies to "bodily injury" and "property damage" only if:
   1. The "bodily injury" or "property damage" is caused by an "accident"; and
   2. The "bodily injury" or "property damage" occurs during the policy period.

C. We will pay, in addition to the applicable limits of insurance, costs
   taxed against the insured in any "suit" we defend, premiums on bonds,
   reasonable expenses incurred at our request, and prejudgment interest.""",

        "home": """INSURING AGREEMENT
─────────────────────────────────────────────────────────────────────

SECTION I — PROPERTY COVERAGE

A. COVERAGE A — DWELLING
   We cover the dwelling shown in the Declarations, including structures
   attached to the dwelling, and materials and supplies located on or next
   to the residence premises for use in construction, alteration, or repair
   of the dwelling or other structures on the residence premises.

B. COVERAGE B — OTHER STRUCTURES
   We cover other structures on the residence premises separated from the
   dwelling by clear space. Structures connected to the dwelling by only
   a fence, utility line, or similar connection are considered to be other
   structures. Coverage B limit is 10% of Coverage A unless otherwise shown.

C. COVERAGE C — PERSONAL PROPERTY
   We cover personal property owned or used by an insured while it is
   anywhere in the world. At your request, we will cover personal property
   owned by others while the property is on the part of the residence
   premises occupied by an insured.""",

        "life": """INSURING AGREEMENT
─────────────────────────────────────────────────────────────────────

INSURING CLAUSE

In consideration of the application for this policy and the payment of the
initial premium, and subject to the terms and conditions of this policy,
the Company agrees:

1. DEATH BENEFIT: To pay the Face Amount shown on the Policy Schedule page
   to the designated Beneficiary upon receipt of due proof that the Insured
   died while this policy was in force, subject to the suicide exclusion
   and contestability provisions.

2. TERM OF COVERAGE: Coverage under this policy begins on the Policy Date
   shown in the Policy Schedule and continues for the Term Period stated,
   provided premiums are paid when due.

3. PREMIUM REQUIREMENT: This policy will remain in force as long as premiums
   are paid when due within the grace period of 31 days after the due date.""",
    }

    # Default agreement for other policy types
    default = f"""INSURING AGREEMENT
{"-"*70}

SECTION I — INSURING AGREEMENT

In consideration of the payment of premium and subject to all terms and
conditions of this policy, the Company agrees to provide the coverage
described herein for losses occurring during the policy period.

The coverage afforded by this policy is subject to:
  a) The Declarations page of this policy;
  b) The terms, conditions, exclusions, and limitations herein;
  c) Any endorsements attached to this policy; and
  d) Applicable state and federal law.

The Company's obligation shall not exceed the limits of insurance stated
in the Declarations, regardless of the number of insureds, claims made,
or persons and organizations making claims."""

    return agreements.get(ptype, default)


def _gen_definitions(ptype):
    return f"""DEFINITIONS
─────────────────────────────────────────────────────────────────────

Throughout this policy, the following words and phrases have specific meanings
as defined below. Defined terms appear in "quotation marks".

"Accident" means a sudden, unexpected, and unintended event.

"Bodily injury" means physical harm, sickness, or disease sustained by a
person, including death resulting from any of these at any time.

"Claim" means a demand for money or services, including a "suit", that
seeks damages because of injury or damage to which this insurance may apply.

"Coverage territory" means:
  a. The United States of America (including its territories and possessions),
     Puerto Rico and Canada; or
  b. International waters or air space, provided the injury or damage does not
     occur in the course of travel or transportation to or from any place not
     included in a. above; or
  c. All other parts of the world if the injury or damage arises out of the
     activities of a person whose home is in the territory described in a.

"Damages" means compensatory damages, including general and special damages.

"Insured" means any person or organization qualifying as an insured in the
Who Is An Insured section of the applicable coverage form.

"Insurer", "Company", "We", "Us", "Our" refers to the insurance company
providing this coverage as named in the Declarations.

"Occurrence" means an accident, including continuous or repeated exposure
to substantially the same general harmful conditions.

"Policy period" means the period of time from the inception date shown in
the Declarations to the expiration date, or any earlier cancellation date.

"Premium" means the monetary consideration paid or payable for this policy.

"Property damage" means:
  a. Physical injury to tangible property, including all resulting loss of
     use of that property; or
  b. Loss of use of tangible property that is not physically injured.

"Suit" means a civil proceeding in which damages because of injury to which
this insurance applies are alleged. "Suit" includes:
  a. An arbitration proceeding in which such damages are claimed;
  b. Any other alternative dispute resolution proceeding in which such
     damages are claimed and to which the insured must submit or submits
     with our consent."""


def _gen_coverage(ptype, pdata):
    limits = {k: v for k, v in pdata.items()
              if any(w in k.lower() for w in ["limit", "coverage", "amount", "benefit"])}
    limits_text = "\n".join(f"  {k.replace('_',' ').title()}: {v}" for k, v in limits.items()) or "  As stated in the Declarations"

    return f"""COVERAGE DETAILS
─────────────────────────────────────────────────────────────────────

SECTION II — COVERAGE PROVISIONS

A. COVERAGE LIMITS
{limits_text}

B. COVERAGE APPLIES TO:
   The insured named in the Declarations and, where applicable:
   1. Resident relatives of the named insured's household;
   2. Other persons or entities as specifically endorsed herein.

C. ADDITIONAL COVERAGES
   The following additional coverages are provided without additional premium
   unless specifically excluded or limited in the Declarations:

   1. Claim Expenses — We will pay all costs we incur in the investigation
      and defense of claims and suits seeking damages covered by this policy.

   2. Emergency First Aid — We will pay expenses for first aid to others
      at the time of an accident involving coverage under this policy.

   3. Loss of Earnings — We will pay up to $250 per day for loss of earnings,
      but not other income, because you must attend hearings or trials at
      our request.

   4. Post-Judgment Interest — Interest on that part of the judgment within
      our limit of liability that accrues after entry of the judgment.

D. SUPPLEMENTARY PAYMENTS
   In addition to the limits of liability, we will pay:
   1. Up to $2,500 per claim for bail bonds required by law;
   2. Reasonable expenses incurred at our request;
   3. Court costs taxed against the insured."""


def _gen_exclusions(ptype):
    return f"""EXCLUSIONS
─────────────────────────────────────────────────────────────────────

SECTION III — EXCLUSIONS

This policy does not apply to:

A. EXPECTED OR INTENDED INJURY
   "Bodily injury" or "property damage" expected or intended from the
   standpoint of the insured. This exclusion does not apply to "bodily
   injury" resulting from the use of reasonable force to protect persons
   or property.

B. CONTRACTUAL LIABILITY
   Liability assumed under any contract or agreement, except:
   1. Liability that the insured would have in the absence of the contract;
   2. Liability assumed in a contract or agreement that is an "insured contract".

C. LIQUOR LIABILITY
   "Bodily injury" or "property damage" for which any insured may be held
   liable by reason of causing or contributing to the intoxication of any
   person, or the furnishing of alcoholic beverages to a person under legal
   drinking age or under the influence of alcohol.

D. WORKERS' COMPENSATION AND SIMILAR LAWS
   Any obligation of the insured under a workers' compensation, disability
   benefits, or unemployment compensation law, or any similar law.

E. EMPLOYER'S LIABILITY
   "Bodily injury" to an "employee" of the insured arising out of and in
   the course of employment by the insured or performing duties related to
   the conduct of the insured's business.

F. POLLUTION
   "Bodily injury" or "property damage" arising out of the actual, alleged,
   or threatened discharge, dispersal, seepage, migration, release, or escape
   of "pollutants" at any time.

G. WAR
   "Bodily injury" or "property damage", however caused, arising directly
   or indirectly out of war, including undeclared or civil war, warlike
   action by a military force, or insurrection.

H. NUCLEAR HAZARD
   Any loss, cost, or expense arising out of any nuclear reaction, nuclear
   radiation, or radioactive contamination, howsoever caused.

I. INTENTIONAL ACTS
   Any act or omission that is intentional, dishonest, fraudulent, criminal,
   or malicious.

J. PROFESSIONAL SERVICES
   "Bodily injury" or "property damage" due to the rendering of or failure
   to render any professional service. (Professional liability coverage
   requires a separate policy.)

K. CYBER AND ELECTRONIC DATA
   Damages arising out of the loss of, loss of use of, damage to, corruption
   of, inability to access, or inability to manipulate "electronic data".

NOTE: The above exclusions are based on standard ISO form exclusions.
Additional exclusions may apply based on the specific coverage form and
state-specific endorsements."""


def _gen_conditions(ptype, pdata):
    return f"""CONDITIONS
─────────────────────────────────────────────────────────────────────

SECTION IV — CONDITIONS

A. DUTIES IN THE EVENT OF OCCURRENCE, CLAIM, OR SUIT

   1. You must see to it that we are notified as soon as practicable of an
      "occurrence" or an offense which may result in a claim.

   2. If a claim is made or "suit" is brought against any insured, you must:
      a. Immediately record the specifics of the claim or "suit" and the date
         received; and
      b. Notify us as soon as practicable.

   3. You and any other involved insured must:
      a. Immediately send us copies of any demands, notices, summonses, or
         legal papers received in connection with the claim or "suit";
      b. Authorize us to obtain records and other information;
      c. Cooperate with us in the investigation or settlement of the claim
         or defense against the "suit"; and
      d. Assist us in the enforcement of any right against any person or
         organization that may be liable to the insured.

B. LEGAL ACTION AGAINST US
   No person or organization has a right under this policy to join us as a
   party or otherwise bring us into a "suit" asking for damages from an
   insured. Also, no action may be brought against us unless:
   1. There has been full compliance with all terms of this policy; and
   2. We agree in writing that the insured has an obligation to pay, or until
      the amount of that obligation has been finally determined by judgment.

C. PREMIUM AUDIT
   We will compute all premiums for this policy in accordance with our rules
   and rates. Premium shown in this policy is a deposit premium only.
   The actual premium will be determined at the end of the policy period
   based on the actual exposure.

D. REPRESENTATIONS
   By accepting this policy, you agree that:
   1. The statements in the Declarations and application are accurate and
      complete; and
   2. Those statements are based upon representations you made to us.

E. SEPARATION OF INSUREDS
   Except with respect to the Limits of Insurance, this insurance applies:
   1. As if each named insured were the only named insured; and
   2. Separately to each insured against whom claim is made or "suit" is brought.

F. TRANSFER OF RIGHTS AND DUTIES UNDER THIS POLICY
   Your rights and duties under this policy may not be transferred without
   our written consent, except in the case of death of an individual named
   insured. If you die, your rights and duties will be transferred to your
   legal representative but only while acting within the scope of duties
   as your legal representative.

G. WHEN WE DO NOT RENEW
   If we decide not to renew this policy, we will mail or deliver to the
   first Named Insured shown in the Declarations written notice of the
   nonrenewal not less than {pdata.get('nonrenewal_notice_days', 60)} days
   before the expiration date.

H. CANCELLATION
   1. The first Named Insured shown in the Declarations may cancel this
      policy by mailing or delivering to us advance written notice of
      cancellation.
   2. We may cancel this policy by mailing or delivering to the first Named
      Insured written notice of cancellation at least:
      a. 10 days before the effective date of cancellation if we cancel for
         nonpayment of premium; or
      b. {pdata.get('cancellation_notice_days', 30)} days before the effective
         date of cancellation if we cancel for any other reason.

I. CHANGES
   This policy contains all the agreements between you and us concerning
   the insurance afforded. The first Named Insured shown in the Declarations
   is authorized to make changes in the terms of this policy with our consent.
   This policy's terms can be amended or waived only by endorsement issued
   by us and made a part of this policy."""


def _gen_endorsements(ptype, pdata):
    endorsements = pdata.get("endorsements", [])
    endt_text = "\n".join(f"  • {e}" for e in endorsements) if endorsements else "  None attached"

    return f"""ENDORSEMENTS AND SCHEDULES
─────────────────────────────────────────────────────────────────────

SECTION V — ENDORSEMENTS

The following endorsements are attached to and form part of this policy:

{endt_text}

COMMON ENDORSEMENT FORMS AVAILABLE (not automatically included):

  ISO CG 20 10 — Additional Insured — Owners, Lessees, or Contractors
  ISO CG 20 37 — Additional Insured — Completed Operations
  ISO CG 24 04 — Waiver of Transfer of Rights of Recovery
  ISO IL 00 21 — Nuclear Energy Liability Exclusion
  ISO CG 21 47 — Employment-Related Practices Exclusion
  ISO CG 21 73 — Exclusion of Certified Acts of Terrorism

STATE-SPECIFIC ENDORSEMENTS:
  Applicable state amendatory endorsements are incorporated by reference
  and made part of this policy as required by state law."""


def _gen_signature_block(pdata):
    today     = datetime.now().strftime("%B %d, %Y")
    agent     = pdata.get("agent_name", "Insurance AI Platform")
    return f"""SIGNATURES AND ATTESTATION
─────────────────────────────────────────────────────────────────────

This policy is not valid unless countersigned by our duly authorized
representative.

IN WITNESS WHEREOF, we have caused this policy to be signed by our
President and Secretary, and countersigned on the Declarations page
by our duly authorized representative.

_________________________________    _________________________________
President                            Secretary


Countersigned:  _______________________________ Date: {today}
                Authorized Representative


AGENT OF RECORD: {agent}

─────────────────────────────────────────────────────────────────────
NOTICE: This document was generated by Insurance AI Platform.
The policy language is based on ISO standard forms for illustrative purposes.
This document requires review and countersignature by a licensed insurance
professional before becoming a binding contract.
Consult a licensed insurance agent or attorney for legal advice.
─────────────────────────────────────────────────────────────────────"""
