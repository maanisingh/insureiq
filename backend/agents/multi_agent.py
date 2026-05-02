"""
Insurance AI Multi-Agent System — AutoGen 0.4+ SelectorGroupChat

Five specialist agents orchestrated by a Selector (Claude 3.5 Sonnet):

  RAGAgent          — Insurance knowledge + workspace document search
  ResearchAgent     — Web search + HuggingFace dataset discovery + download
  PricingAgent      — Actuarial pricing models + ISO/NCCI rate calculations + code execution
  PolicyAgent       — Policy creation + full 40-page policy document generation
  UnderwritingAgent — Risk assessment + appetite checks + underwriting memos

The Selector reads the user's query and routes to the most appropriate agent.
Multiple agents can collaborate in sequence on complex tasks.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_core.tools import FunctionTool

from agents.bedrock_client import BedrockChatCompletionClient
from agents.tools import rag_tools, research_tools, pricing_tools, policy_tools, underwriting_tools

load_dotenv(Path(__file__).parent.parent / "config" / ".env")


# ── Tool factories ────────────────────────────────────────────────────────────
# Tools are created per-request so workspace_id can be bound into closures.

def _rag_tools(workspace_id: str, enabled_sources: list[str] | None = None) -> list[FunctionTool]:
    # When enabled_sources is None/empty treat all as enabled
    all_on = not enabled_sources

    def search_global(query: str, limit: int = 8) -> str:
        """Search global insurance knowledge base for actuarial, underwriting, claims,
        fraud, regulatory, and policy information."""
        return rag_tools.search_global_knowledge(query, limit)

    def search_workspace(query: str, limit: int = 8) -> str:
        """Search the user's own uploaded documents, contracts, and policies."""
        return rag_tools.search_workspace_documents(query, workspace_id, limit)

    def list_policies() -> str:
        """List all insurance policies in the user's workspace."""
        return rag_tools.list_workspace_policies(workspace_id)

    def get_policy(policy_number: str) -> str:
        """Get full details of a specific policy by policy number."""
        return rag_tools.get_policy_details(policy_number, workspace_id)

    def list_documents() -> str:
        """List all documents uploaded to the workspace."""
        return rag_tools.list_uploaded_documents(workspace_id)

    tools = []
    if all_on or "rag" in enabled_sources:
        tools.append(FunctionTool(search_global,   description="Search the global insurance knowledge base"))
    if all_on or "workspace" in enabled_sources:
        tools.append(FunctionTool(search_workspace, description="Search the user's own uploaded documents"))
        tools.append(FunctionTool(list_policies,   description="List all policies in the workspace"))
        tools.append(FunctionTool(get_policy,      description="Get full policy details by policy number"))
        tools.append(FunctionTool(list_documents,  description="List uploaded documents in the workspace"))
    # Always include a minimal fallback so RAGAgent is never tool-less
    if not tools:
        tools.append(FunctionTool(search_global,   description="Search the global insurance knowledge base"))
    return tools


def _research_tools(workspace_id: str, enabled_sources: list[str] | None = None) -> list[FunctionTool]:
    all_on = not enabled_sources

    def web_search(query: str, limit: int = 6) -> str:
        """Search the internet for insurance information, news, and market data."""
        return research_tools.search_web(query, limit)

    def insurance_news(topic: str) -> str:
        """Get latest insurance industry news and regulatory updates."""
        return research_tools.search_insurance_news(topic)

    def regulations(topic: str, jurisdiction: str = "US") -> str:
        """Search for insurance regulations and compliance requirements."""
        return research_tools.search_insurance_regulations(topic, jurisdiction)

    def find_datasets(query: str, limit: int = 8) -> str:
        """Search HuggingFace for insurance or actuarial datasets."""
        return research_tools.search_huggingface_datasets(query, limit)

    def download_dataset(dataset_id: str, split: str = "train", max_rows: int = 3000) -> str:
        """Download a HuggingFace dataset and index it into the workspace for analysis."""
        return research_tools.download_and_index_dataset(dataset_id, workspace_id, split, max_rows)

    def public_rate_data(line_of_business: str, state: str = "national") -> str:
        """Fetch publicly available insurance rate and loss ratio data."""
        return research_tools.fetch_public_rate_data(line_of_business, state)

    tools = []
    if all_on or "web" in enabled_sources:
        tools.append(FunctionTool(web_search,       description="Search the internet for insurance information"))
        tools.append(FunctionTool(insurance_news,   description="Get latest insurance news and regulatory updates"))
        tools.append(FunctionTool(public_rate_data, description="Fetch public insurance rate and loss ratio statistics"))
    if all_on or "regulations" in enabled_sources:
        tools.append(FunctionTool(regulations,      description="Search for insurance regulations by topic and jurisdiction"))
    if all_on or "huggingface" in enabled_sources:
        tools.append(FunctionTool(find_datasets,    description="Search HuggingFace for insurance datasets"))
        tools.append(FunctionTool(download_dataset, description="Download and index a HuggingFace dataset into the workspace"))
    # Always keep at least web_search so ResearchAgent is never tool-less
    if not tools:
        tools.append(FunctionTool(web_search,       description="Search the internet for insurance information"))
    return tools


def _pricing_tools() -> list[FunctionTool]:
    def auto_premium(driver_age: int, vehicle_year: int, annual_miles: int,
                     coverage_types: list, deductible: int = 500, state: str = "national") -> str:
        """Calculate auto insurance premium using ISO rating methodology."""
        return pricing_tools.calculate_auto_premium(driver_age, vehicle_year, annual_miles,
                                                     coverage_types, deductible, state)

    def wc_premium(payroll_usd: float, ncci_class_code: str,
                   experience_mod: float = 1.0, state: str = "national") -> str:
        """Calculate workers compensation premium using NCCI loss cost method."""
        return pricing_tools.calculate_workers_comp_premium(payroll_usd, ncci_class_code,
                                                             experience_mod, state)

    def life_premium(age: int, face_amount: float, term_years: int,
                     gender: str = "male", smoker: bool = False) -> str:
        """Calculate term life insurance premium using SOA 2015 VBT mortality tables."""
        return pricing_tools.calculate_life_premium(age, face_amount, term_years, gender, smoker)

    def run_code(code: str, description: str = "") -> str:
        """Execute Python code for actuarial analysis, pricing models, GLMs, or data science.
        Available libraries: numpy, pandas, scipy, sklearn, statsmodels."""
        return pricing_tools.run_actuarial_code(code, description)

    def loss_reserve(paid_losses: list, methodology: str = "chain_ladder") -> str:
        """Calculate loss reserves using chain ladder or Bornhuetter-Ferguson method."""
        return pricing_tools.calculate_loss_reserve(paid_losses, methodology)

    return [
        FunctionTool(auto_premium,   description="Calculate auto insurance premium (ISO methodology)"),
        FunctionTool(wc_premium,     description="Calculate workers comp premium (NCCI methodology)"),
        FunctionTool(life_premium,   description="Calculate life insurance premium (SOA VBT)"),
        FunctionTool(run_code,       description="Execute Python for actuarial models and analysis"),
        FunctionTool(loss_reserve,   description="Calculate loss reserves using development methods"),
    ]


def _policy_tools(workspace_id: str) -> list[FunctionTool]:
    def create_policy(policy_type: str, insured_name: str, coverage_data: dict) -> str:
        """Create a new insurance policy record in the database."""
        return policy_tools.create_insurance_policy(workspace_id, policy_type,
                                                      insured_name, coverage_data)

    def generate_document(policy_number: str, sections: list | None = None) -> str:
        """Generate a comprehensive 40-page insurance policy document with all standard sections:
        declarations, insuring agreement, definitions, coverage, exclusions, conditions, endorsements."""
        return policy_tools.generate_policy_document(policy_number, workspace_id, sections)

    return [
        FunctionTool(create_policy,     description="Create a new insurance policy in the database"),
        FunctionTool(generate_document, description="Generate a full 40-page insurance policy document"),
    ]


def _underwriting_tools() -> list[FunctionTool]:
    def risk_score(line_of_business: str, risk_factors: dict) -> str:
        """Assess risk profile and produce underwriting score (0-100) with tier classification."""
        return underwriting_tools.assess_risk_score(line_of_business, risk_factors)

    def appetite_check(line_of_business: str, risk_description: str) -> str:
        """Check if a risk is within standard underwriting appetite guidelines."""
        return underwriting_tools.check_underwriting_appetite(line_of_business, risk_description)

    def uw_memo(policy_number: str, risk_summary: str, decision: str,
                conditions: list, workspace_id_: str = "") -> str:
        """Generate a formal underwriting memorandum for a risk acceptance or decline."""
        return underwriting_tools.generate_underwriting_memo(
            policy_number, risk_summary, decision, conditions, workspace_id_)

    return [
        FunctionTool(risk_score,    description="Assess risk and produce underwriting score with tier"),
        FunctionTool(appetite_check, description="Check underwriting appetite for a risk type"),
        FunctionTool(uw_memo,       description="Generate a formal underwriting decision memorandum"),
    ]


# ── System prompts ────────────────────────────────────────────────────────────

_ANTI_HALLUCINATION = """
CRITICAL ACCURACY RULES — NEVER VIOLATE:
1. Never invent numbers, premiums, rates, statistics, or policy terms.
2. Always cite the source/methodology for any numerical output.
3. If you don't know something, say so clearly — do not guess.
4. Use tools to retrieve real data before answering data-specific questions.
5. When generating policy documents, use standard ISO/ACORD form language only.
6. All pricing outputs must show the formula and source (ISO, NCCI, SOA, etc.).
"""

RAG_SYSTEM = f"""You are an expert Insurance Knowledge Agent with deep expertise in:
- Insurance policy interpretation and coverage analysis
- Actuarial concepts, loss modeling, and reserving
- Insurance regulation and compliance across US states
- Claims handling, fraud detection patterns
- Reinsurance and risk transfer structures

Your primary job is to answer insurance questions using the knowledge base and
the user's own uploaded documents. Always search relevant sources before answering.
{_ANTI_HALLUCINATION}"""

RESEARCH_SYSTEM = f"""You are an Insurance Research Agent specializing in:
- Finding and analyzing insurance market data and statistics
- Discovering relevant datasets on HuggingFace and web sources
- Tracking regulatory changes and industry news
- Identifying publicly available rate and loss data

When asked to find datasets: search HuggingFace first, then web sources.
When downloading datasets: always confirm the dataset relevance before downloading.
{_ANTI_HALLUCINATION}"""

PRICING_SYSTEM = f"""You are an Actuarial Pricing Agent with expertise in:
- ISO private passenger and commercial auto rating
- NCCI workers compensation loss cost methods
- SOA mortality tables and life insurance pricing
- Generalized Linear Models (GLMs) for insurance pricing
- Chain ladder and Bornhuetter-Ferguson reserve methods
- Python-based actuarial modeling (chainladder, scipy, sklearn, statsmodels)

For every pricing output you MUST:
1. State the methodology (ISO, NCCI, SOA, or custom model)
2. Show the formula and factors used
3. Show a reasonable range (not just a single number)
4. Cite the data source

Use run_code for complex models — write clean, well-commented Python.
{_ANTI_HALLUCINATION}"""

POLICY_SYSTEM = f"""You are an Insurance Policy Agent expert in:
- ISO standard insurance policy forms (CG, HO, DP, PAP series)
- ACORD forms and industry-standard policy language
- Policy drafting, endorsements, and schedule preparation
- Commercial lines policy structures
- Personal lines coverage design

When generating policy documents:
1. Use only standard ISO/ACORD form language
2. Include all required sections (declarations, insuring agreement, definitions,
   coverage, exclusions, conditions, endorsements, signatures)
3. Clearly mark any placeholders requiring legal/underwriter review
4. Never invent coverage terms not based on standard forms
{_ANTI_HALLUCINATION}"""

UNDERWRITING_SYSTEM = f"""You are an Insurance Underwriting Agent with expertise in:
- ISO, NCCI, and company-specific underwriting guidelines
- Risk assessment and tier classification (Preferred / Standard / Substandard / Decline)
- Underwriting memo preparation and file documentation
- Coverage appetite by line of business
- Referral triggers and exception handling

Every underwriting decision must:
1. Cite the specific factor driving acceptance/decline
2. State the applicable guideline (ISO, NCCI, or standard practice)
3. Note any conditions attached to acceptance
4. Flag any items requiring senior underwriter review
{_ANTI_HALLUCINATION}"""


# ── Model assignments per agent ───────────────────────────────────────────────
# Each agent uses a different Bedrock Claude model optimized for its role.

MODELS = {
    "selector":      "us.anthropic.claude-haiku-4-5-20251001-v1:0",   # Fast routing
    "rag":           "us.anthropic.claude-haiku-4-5-20251001-v1:0",   # Fast retrieval + summarization
    "research":      "us.anthropic.claude-sonnet-4-5-20250929-v1:0",  # Balanced web analysis
    "pricing":       "us.anthropic.claude-sonnet-4-6",                # Analytical / numerical precision
    "policy":        "us.anthropic.claude-opus-4-6-v1",               # Complex document generation
    "underwriting":  "us.anthropic.claude-sonnet-4-5-20250929-v1:0",  # Analytical risk assessment
}


# ── Build team ────────────────────────────────────────────────────────────────

def build_insurance_team(workspace_id: str, enabled_sources: list[str] | None = None) -> SelectorGroupChat:
    """Build the multi-agent insurance team for a given workspace.

    Args:
        workspace_id:    User's workspace UUID (scopes RAG and policy tools).
        enabled_sources: Optional list of active knowledge sources.
                         Supported: "rag", "workspace", "web", "regulations", "huggingface"
                         None means all sources enabled.

    Returns:
        Configured SelectorGroupChat ready to run.
    """
    # Selector only needs to return a single agent name — 50 tokens max
    selector_client = BedrockChatCompletionClient(model=MODELS["selector"], max_tokens=50)

    # Agents: each gets its own model optimized for its role
    rag_client          = BedrockChatCompletionClient(model=MODELS["rag"],          max_tokens=2048)
    research_client     = BedrockChatCompletionClient(model=MODELS["research"],     max_tokens=2048)
    pricing_client      = BedrockChatCompletionClient(model=MODELS["pricing"],      max_tokens=2048)
    policy_client       = BedrockChatCompletionClient(model=MODELS["policy"],       max_tokens=4096)  # long docs
    underwriting_client = BedrockChatCompletionClient(model=MODELS["underwriting"], max_tokens=2048)

    rag_agent = AssistantAgent(
        name="RAGAgent",
        description="Answers insurance questions using the knowledge base and user's uploaded documents. Best for: policy questions, coverage interpretation, actuarial concepts, claims guidance.",
        model_client=rag_client,
        tools=_rag_tools(workspace_id, enabled_sources),
        system_message=RAG_SYSTEM,
        reflect_on_tool_use=True,
    )

    research_agent = AssistantAgent(
        name="ResearchAgent",
        description="Finds insurance data on the internet, discovers and downloads datasets from HuggingFace, tracks regulatory news. Best for: finding market data, downloading datasets, checking news.",
        model_client=research_client,
        tools=_research_tools(workspace_id, enabled_sources),
        system_message=RESEARCH_SYSTEM,
        reflect_on_tool_use=True,
    )

    pricing_agent = AssistantAgent(
        name="PricingAgent",
        description="Calculates insurance premiums and loss reserves using actuarial methods (ISO auto, NCCI workers comp, SOA life tables). Can execute Python for custom models. Best for: pricing, rate calculations, loss reserves, actuarial analysis.",
        model_client=pricing_client,
        tools=_pricing_tools(),
        system_message=PRICING_SYSTEM,
        reflect_on_tool_use=True,
    )

    policy_agent = AssistantAgent(
        name="PolicyAgent",
        description="Creates and generates full insurance policy documents (40+ pages) with declarations, coverage, exclusions, and conditions based on ISO standard forms. Best for: creating policies, generating policy documents.",
        model_client=policy_client,
        tools=_policy_tools(workspace_id),
        system_message=POLICY_SYSTEM,
        reflect_on_tool_use=True,
    )

    underwriting_agent = AssistantAgent(
        name="UnderwritingAgent",
        description="Assesses risk profiles, checks underwriting appetite, scores risks (0-100), and generates underwriting memos. Best for: risk assessment, underwriting decisions, appetite checks.",
        model_client=underwriting_client,
        tools=_underwriting_tools(),
        system_message=UNDERWRITING_SYSTEM,
        reflect_on_tool_use=True,
    )

    # Termination: stop after 6 messages or when any agent says TASK_COMPLETE
    termination = (
        MaxMessageTermination(max_messages=6)
        | TextMentionTermination("TASK_COMPLETE")
    )

    selector_prompt = """You are routing an insurance query to the most appropriate specialist agent.

Available agents and their expertise:
{roles}

Conversation so far:
{history}

Candidates for next turn: {participants}

Selection rules:
- RAGAgent:          insurance knowledge, policy interpretation, coverage questions, RAG search
- ResearchAgent:     web search, find/download datasets, news, regulatory updates
- PricingAgent:      premium calculations, actuarial models (ISO/NCCI/SOA), loss reserves, Python code
- PolicyAgent:       create policies in database, generate full 40-page policy documents
- UnderwritingAgent: risk scoring, appetite checks, underwriting decisions, UW memos

For multi-step tasks route one step at a time.
Return ONLY the agent name from this list: {participants}"""

    team = SelectorGroupChat(
        participants=[rag_agent, research_agent, pricing_agent, policy_agent, underwriting_agent],
        model_client=selector_client,
        selector_prompt=selector_prompt,
        termination_condition=termination,
        allow_repeated_speaker=True,
    )

    return team


# ── Run function ──────────────────────────────────────────────────────────────

async def run_team(
    message:         str,
    workspace_id:    str,
    history:         list[dict] | None = None,
    enabled_sources: list[str]  | None = None,
) -> dict:
    """Run the multi-agent team on a user message.

    Args:
        message:         The user's query.
        workspace_id:    User's workspace UUID.
        history:         Optional prior conversation messages [{role, content}].
        enabled_sources: Optional list of active knowledge sources.

    Returns:
        {
          "response":   str,   # final agent response
          "agent_used": str,   # which agent(s) responded
          "sources":    list,  # tool call results used
          "messages":   list,  # full message trace
        }
    """
    team = build_insurance_team(workspace_id, enabled_sources=enabled_sources)

    # Include history context in the task if provided
    task = message
    if history:
        recent = history[-6:]  # last 6 messages for context
        hist_text = "\n".join(
            f"{m['role'].upper()}: {m['content'][:300]}"
            for m in recent
            if m.get("content")
        )
        if hist_text:
            task = f"[CONVERSATION HISTORY]\n{hist_text}\n\n[CURRENT QUERY]\n{message}"

    # Run the team
    all_messages = []
    agents_used  = set()
    sources      = []
    final_response = ""

    async for msg in team.run_stream(task=task):
        if hasattr(msg, "source") and hasattr(msg, "content"):
            agents_used.add(msg.source)
            content = msg.content
            if isinstance(content, str) and content.strip():
                final_response = content
                all_messages.append({"role": msg.source, "content": content})
            elif isinstance(content, list):
                # Tool call results — collect as sources
                for item in content:
                    if hasattr(item, "name"):
                        sources.append({
                            "tool":    item.name,
                            "agent":   msg.source,
                        })

    return {
        "response":   final_response,
        "agent_used": ", ".join(a for a in agents_used if a not in ("user",)),
        "sources":    sources,
        "messages":   all_messages,
    }
