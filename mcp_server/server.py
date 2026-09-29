"""
MCP server for JK Assistance: exposes the AJK student-services knowledge base and rule engines as MCP tools,
so any MCP-capable agent (Claude Desktop, Claude Code, ...) can answer admission, document, fee, deadline and
semester-promotion questions for UAJK, MUST and the AJK medical colleges - grounded in official sources.

Run directly (stdio):
    python mcp_server\\server.py
Run over HTTP (streamable-http) for remote clients / the MCP Inspector:
    python mcp_server\\server.py --http          (listens on http://localhost:8765/mcp)

Add to an MCP client config (Claude Desktop claude_desktop_config.json, or Claude Code .mcp.json):
    {
      "mcpServers": {
        "jk-assistance": {
          "command": "python",
          "args": ["C:\\Users\\Faisal Ramzan\\Desktop\\AJK university VA\\mcp_server\\server.py"],
          "env": {"JK_DISABLE_LLM": "1"}
        }
      }
    }
JK_DISABLE_LLM=1 makes the tools return rule-engine results + evidence only (the calling agent does the writing).
"""
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from jk_assistance import advisor, applications, assistant, monitor, progression, store  # noqa: E402
from jk_assistance.config import today  # noqa: E402
from jk_assistance.decision import triage  # noqa: E402
from jk_assistance.knowledge import get_knowledge  # noqa: E402

mcp = MCPServer("jk-assistance", instructions=(
    "JK Assistance: official admission, document, fee/challan, deadline and semester-promotion information for "
    "the University of Azad Jammu & Kashmir (uajk), Mirpur University of Science & Technology (must), the AJK public "
    "medical colleges (JAC admissions: jac; Poonch Medical College: pmc; MBBSMC Mirpur: mbbsmc; AJKMC: ajkmc) and "
    "UHS Lahore (uhs) for MBBS/BDS degrees and transcripts. Every fee carries its effective date and source; items with "
    "trust='secondary' come from third-party sites and must be presented as 'to be verified'. When a tool returns "
    "action=ESCALATE or rules_unavailable, tell the user a university official must decide and give the contact."
))

kb = get_knowledge()  # build the index once at start-up


@mcp.tool()
def list_services(institution: str = "") -> list:
    """List student-service procedures (degree, transcript/DMC, verification, duplicate degree, migration, transfer,
    clearance, bonafide, English proficiency, re-checking, refund, convocation, hostel...) with their ids.
    institution: one of uajk, must, uhs (empty = all)."""
    return [{"id": s["id"], "institution": s["institution"], "name": s["name"]} for s in kb.services.values()
            if not institution or s["institution"] == institution]


@mcp.tool()
def get_service(service_id: str) -> dict:
    """Full checklist for one procedure: required documents, steps, office, forms (with URLs), the fee version in
    force today (with previous versions), deadlines, processing time and sources. Get ids from list_services."""
    if service_id not in kb.services:
        return {"error": f"unknown service_id; call list_services. Known: {', '.join(kb.services)}"}
    return assistant._service_card(kb.services[service_id], kb, today())


@mcp.tool()
def search_knowledge(query: str, institution: str = "", k: int = 6) -> list:
    """BM25 search over all official pages, forms, prospectuses and the curated rules. Returns evidence snippets
    with source URL and trust level. Use for anything not covered by the structured tools."""
    return [{"score": round(s, 2), "source": c.source, "trust": c.trust, "kind": c.kind, "text": c.text[:1500]}
            for s, c in kb.search(query, institution or None, k=k)]


@mcp.tool()
def advise_admission(group: str, hssc_percent: float, ssc_percent: float = -1, mdcat_percent: float = -1,
                     interests: str = "", institutions: str = "", age: int = 0, state_subject: bool = True,
                     studied_math: bool = False) -> dict:
    """Admission advice for a student who completed 12 years of education. group: pre_med | pre_eng | ics | fa |
    icom | general_science | dae | a_level. interests: free text or comma-separated fields (computing, engineering,
    medicine, dentistry, health, sciences, social_sciences, business, law, education, arts). institutions:
    comma-separated (uajk, must, jac). Returns eligible programs, heuristic chance, tests, fees, documents,
    how to apply and upcoming deadlines. Use -1 / 0 for unknown numbers."""
    profile = {"group": group, "hssc_percent": hssc_percent, "state_subject": state_subject, "studied_math": studied_math}
    if ssc_percent >= 0:
        profile["ssc_percent"] = ssc_percent
    if mdcat_percent >= 0:
        profile["mdcat_percent"] = mdcat_percent
    if age:
        profile["age"] = age
    if interests:
        profile["interests"] = [i.strip() for i in interests.split(",") if i.strip()]
    if institutions:
        profile["institutions"] = [i.strip() for i in institutions.split(",") if i.strip()]
    return assistant._trim_advice(advisor.advise(profile, kb))


@mcp.tool()
def get_deadlines(institution: str = "", audience: str = "", include_past_days: int = 30) -> dict:
    """Dated deadlines (admission last dates, merit lists, scholarship dates) with days left, plus relative rules
    (fee fine windows, re-checking windows, registration, refund, migration submission). audience: applicants or empty."""
    dl = advisor.upcoming_deadlines(kb, today(), audience=audience or None, include_past_days=include_past_days)
    rules = list(kb.relative_rules.values())
    if institution:
        dl = [d for d in dl if d["institution"] == institution]
        rules = [r for r in rules if r["institution"] == institution]
    return {"today": today().isoformat(), "dated": dl, "rules": rules}


@mcp.tool()
def evaluate_progression(semesters: list, program_type: str = "bs4", institution: str = "must") -> dict:
    """Apply semester promotion rules to a transcript. semesters: [{"number": 1, "courses": [{"code": "CS-101",
    "credits": 3, "percent": 72, "attendance": 90, "lab_percent": null}], "summer": [...]}]. percent null = pending.
    Returns per-semester outcome (promoted/probation/dropped/relegated/pending), probation state, GPA/CGPA.
    Only MUST rules are published; other institutions return rules_unavailable (escalate)."""
    return progression.evaluate({"institution": institution, "program_type": program_type, "semesters": semesters})


@mcp.tool()
def student_dashboard(student_id: str) -> dict:
    """Proactive scan for a stored student/applicant: findings routed to GUIDE / ASK_INFO / ALERT / ESCALATE
    (dues and fines, deadlines, attendance, probation risk, re-checking windows, application deadlines)."""
    s = store.get("students", student_id)
    if not s:
        return {"error": "unknown student_id", "known": [x["id"] for x in store.load("students")]}
    return {"student": {k: s.get(k) for k in ("id", "name", "type", "institution", "program")},
            "findings": triage(monitor.scan(s), student_id)}


@mcp.tool()
def start_application(service_id: str, student_id: str = "") -> dict:
    """Open a tracked application case (document checklist, fees in force today, forms, steps) for a service."""
    try:
        return applications.create(service_id, student_id or None)
    except KeyError as e:
        return {"error": str(e)}


@mcp.tool()
def ask_jk_assistance(message: str, student_id: str = "") -> dict:
    """Full assistant pipeline for a free-text question: routing, rule engines, evidence retrieval, decision
    (GUIDE/ASK_INFO/ALERT/ESCALATE). Returns the answer markdown, action and citations."""
    return assistant.answer(message, student_id or None)


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", port=int(os.environ.get("JK_MCP_PORT", "8765")))
    else:
        mcp.run()
