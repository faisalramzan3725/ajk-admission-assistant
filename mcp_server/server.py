"""
MCP server for JK Assistance (admissions): lets Claude Desktop, Claude Code or any MCP client guide AJK students
after 12 years of education - which programs they are eligible for, the entry tests (MDCAT out of 180, ECAT out of 400),
documents, fees, step-by-step application and admission dates - grounded in official sources.

Run (stdio):             python mcp_server\\server.py
Run (streamable HTTP):   python mcp_server\\server.py --http     -> http://localhost:8765/mcp

Client config (Claude Desktop claude_desktop_config.json / Claude Code .mcp.json):
    {"mcpServers": {"jk-assistance": {"command": "python",
        "args": ["C:\\Users\\Faisal Ramzan\\Desktop\\AJK university VA\\mcp_server\\server.py"],
        "env": {"JK_DISABLE_LLM": "1"}}}}
"""
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from jk_assistance import advisor, assistant  # noqa: E402
from jk_assistance.config import today  # noqa: E402
from jk_assistance.knowledge import get_knowledge  # noqa: E402

mcp = MCPServer("jk-assistance", instructions=(
    "JK Assistance - admission guidance for students in Azad Jammu & Kashmir after 12 years of education. Institutions: "
    "uajk (University of AJK), must (Mirpur University), jac (AJK public MBBS/BDS - its website jac.ajk.gov.pk is NOT working; "
    "use the working channels returned by how_to_apply), szabmu (federal medical colleges with AJK-quota seats). Tests: mdcat "
    "(max 180; MBBS >= 99, BDS >= 90), ecat (max 400; PEC >= 132), uajk_entry_test, must_seet, hec_lat. Always show required vs "
    "obtained marks, and mark trust='secondary' facts as 'verify'. Admissions only."
))
kb = get_knowledge()


def _score(obtained: float, total: float = 0):
    return None if obtained < 0 else ({"obtained": obtained, "total": total} if total else obtained)


@mcp.tool()
def check_admission(group: str, hssc_obtained: float, hssc_total: float = 0, ssc_obtained: float = -1, ssc_total: float = 0,
                    mdcat_obtained: float = -1, ecat_obtained: float = -1, uajk_test_percent: float = -1, seet_percent: float = -1,
                    lat_percent: float = -1, interests: str = "", institutions: str = "", age: int = 0,
                    state_subject: bool = True, studied_math: bool = False) -> dict:
    """Programs a student can apply to, each with an eligibility checklist (criterion / required / yours / pass-fail-pending),
    MBBS/BDS merit aggregate, heuristic chance, fees and how to apply.
    group: pre_med | pre_eng | ics | fa | icom | general_science | dae | a_level.
    hssc/ssc: obtained marks with total (e.g. 946 of 1100), or obtained as a percentage with total 0.
    mdcat_obtained: out of 180; ecat_obtained: out of 400; other tests as percentages. Use -1 when not taken.
    interests: comma-separated (medicine, dentistry, health, engineering, computing, sciences, social_sciences, business, law...).
    institutions: comma-separated subset of uajk, must, jac, szabmu."""
    tests = {k: v for k, v in {"mdcat": _score(mdcat_obtained, 180), "ecat": _score(ecat_obtained, 400), "uajk_entry_test": _score(uajk_test_percent),
                               "must_seet": _score(seet_percent), "hec_lat": _score(lat_percent)}.items() if v is not None}
    profile = {"group": group, "hssc": _score(hssc_obtained, hssc_total), "tests": tests, "state_subject": state_subject, "studied_math": studied_math}
    if ssc_obtained >= 0:
        profile["ssc"] = _score(ssc_obtained, ssc_total)
    if age:
        profile["age"] = age
    if interests:
        profile["interests"] = [i.strip() for i in interests.split(",") if i.strip()]
    if institutions:
        profile["institutions"] = [i.strip() for i in institutions.split(",") if i.strip()]
    return assistant._trim(advisor.advise(profile, kb))


@mcp.tool()
def get_test(test_id: str) -> dict:
    """Entry test details: max marks, passing marks (as % and x/max), format, fee, dates, merit formula, reference averages.
    test_id: mdcat | ecat | uajk_entry_test | must_seet | hec_lat"""
    return advisor.test_info(test_id, kb) if test_id in kb.tests else {"error": f"unknown test; one of {list(kb.tests)}"}


@mcp.tool()
def how_to_apply(institution: str) -> dict:
    """Step-by-step application process, document checklist, contacts, fees rules and upcoming dates.
    institution: uajk | must | jac (MBBS/BDS in AJK, including SZABMU federal colleges)."""
    return advisor.how_to_apply(institution, kb) if institution in kb.processes else {"error": "institution must be uajk, must or jac"}


@mcp.tool()
def admission_dates(institution: str = "", include_past_days: int = 45) -> dict:
    """Admission dates with days left (last dates, merit lists, MDCAT schedule) and admission rules."""
    dl = advisor.upcoming_deadlines(kb, today(), include_past_days=include_past_days)
    return {"today": today().isoformat(), "dated": [d for d in dl if not institution or d["institution"] == institution],
            "rules": [r for r in kb.rules if not institution or r["institution"] == institution]}


@mcp.tool()
def list_programs(institution: str = "", field: str = "") -> list:
    """Programs with eligibility rules and first-semester fees. field: computing, engineering, medicine, health, sciences..."""
    return [p for p in kb.programs.values() if (not institution or p["institution"] == institution) and (not field or p["field"] == field)]


@mcp.tool()
def search_admission_sources(query: str, institution: str = "", k: int = 6) -> list:
    """Evidence search over the official admission pages, prospectuses and PM&DC/SZABMU documents."""
    return [{"score": round(s, 2), "source": c.source, "trust": c.trust, "text": c.text[:1500]} for s, c in kb.search(query, institution or None, k=k)]


@mcp.tool()
def ask_jk_assistance(message: str) -> dict:
    """The full assistant for a free-text admission question (English or Roman Urdu)."""
    return assistant.answer(message)


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", port=int(os.environ.get("JK_MCP_PORT", "8765")))
    else:
        mcp.run()
