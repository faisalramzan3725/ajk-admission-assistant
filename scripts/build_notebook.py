"""Build (and optionally execute) notebooks/JK_Assistance_Samples.ipynb.

Usage:
  python scripts/build_notebook.py            # build + execute, saving outputs
  python scripts/build_notebook.py --no-run   # build only
"""
import sys
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks" / "JK_Assistance_Samples.ipynb"

cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip()))  # noqa: E731
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))  # noqa: E731

md("""
# JK Assistance - sample tests

This notebook exercises every part of JK Assistance with sample inputs:

1. Knowledge base overview
2. Procedures: degree, transcript, migration, clearance (with versioned fees)
3. Admission advisor for students after 12 years of education
4. Semester promotion engine (probation, summer waiver, drop, relegation) and the GPA worked examples
5. What-if simulation
6. Proactive student dashboards (GUIDE / ASK_INFO / ALERT / ESCALATE)
7. Event-driven monitoring (a payment clears an alert)
8. Application tracking with a relative deadline
9. The chat pipeline on many sample questions
10. Evidence search and the human-advisor queue
11. The MCP server, called through the official client
12. (Optional) Claude-written answers, if `ANTHROPIC_API_KEY` is set

It runs on an **isolated temporary copy** of the fictional demo data, with "today" fixed at **2026-09-29**, so results are reproducible and `data/` is never modified.
""")

code(r"""
import os, sys, subprocess, tempfile, json
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
os.environ["JK_TODAY"] = "2026-09-29"
os.environ["JK_DATA_DIR"] = tempfile.mkdtemp(prefix="jk-notebook-")
USE_CLAUDE = bool(os.environ.get("ANTHROPIC_API_KEY"))
if not USE_CLAUDE:
    os.environ["JK_DISABLE_LLM"] = "1"
sys.path.insert(0, str(ROOT))
subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_demo.py")], check=True, env=os.environ, capture_output=True)

import pandas as pd
from IPython.display import Markdown, display
pd.set_option("display.max_colwidth", 90)

from jk_assistance import advisor, applications, assistant, monitor, progression, store
from jk_assistance.decision import triage
from jk_assistance.knowledge import get_knowledge

kb = get_knowledge()
print("Project:", ROOT)
print("Claude answers:", "ON" if USE_CLAUDE else "OFF (rule-engine rendering)")
""")

md("## 1. Knowledge base overview")
code(r"""
print(f"{len(kb.institutions)} institutions, {len(kb.services)} services, {len(kb.programs)} admission programs, "
      f"{len(kb.dated_deadlines)} dated deadlines, {len(kb.relative_rules)} deadline rules, {len(kb.chunks)} evidence chunks")
pd.DataFrame([{"institution": s["institution"], "service": s["name"], "fees": len(s.get("fees", [])),
               "documents": len(s.get("required_documents", [])), "trust": s.get("trust")} for s in kb.services.values()])
""")
code(r"""
pd.Series([c.kind for c in kb.chunks]).value_counts().rename("evidence chunks by kind").to_frame()
""")

md("## 2. Procedures - checklists with the fee in force today")
code(r"""
r = assistant.answer("How do I get my degree from MUST?")
print(r["intent"], r["action"]); display(Markdown(r["answer"]))
""")
code(r"""
display(Markdown(assistant.answer("UAJK migration certificate documents and fee")["answer"]))
""")
code(r"""
display(Markdown(assistant.answer("MBBS transcript from UHS")["answer"]))
""")

md("### Versioned fees - the same question on different dates")
code(r"""
from datetime import date
fee = next(f for f in kb.services["must.degree"]["fees"] if f["item"].startswith("Degree before convocation"))
pd.DataFrame([{"question date": d, "fee in force": kb.fee_version(fee, date.fromisoformat(d))["amount"],
               "effective from": kb.fee_version(fee, date.fromisoformat(d))["effective_from"]}
              for d in ["2025-01-15", "2026-07-27", "2026-07-28", "2026-09-29"]])
""")

md("## 3. Admission advisor - students after 12 years of education")
code(r"""
def advice_table(profile, n=12):
    r = advisor.advise(profile)
    rows = [{"program": p["program"][:60], "inst": p["institution"].upper(), "eligibility": p["eligibility"], "chance": p["chance"],
             "tests": ", ".join(t["id"] for t in p["tests"]) or "-",
             "1st sem fee": (p["fees"] or {}).get("first_semester"), "aggregate": p["merit_aggregate"]} for p in r["programs"]]
    return pd.DataFrame(rows).head(n)

print("Sample A: FSc pre-medical 82%, matric 88%, MDCAT 71%, wants medicine / health")
advice_table({"group": "pre_med", "hssc_percent": 82, "ssc_percent": 88, "mdcat_percent": 71, "interests": ["medicine", "health"]})
""")
code(r"""
print("Sample B: ICS 64%, wants computing")
advice_table({"group": "ics", "hssc_percent": 64, "interests": ["computing"]})
""")
code(r"""
print("Sample C: FA 58%, wants law / social sciences / business, only MUST")
advice_table({"group": "fa", "hssc_percent": 58, "interests": ["law", "social_sciences", "business"], "institutions": ["must"]})
""")
code(r"""
print("Sample D: pre-engineering 56% wants engineering (below the 60% minimum) - shows why not eligible")
r = advisor.advise({"group": "pre_eng", "hssc_percent": 56, "interests": ["engineering"]})
pd.DataFrame([{"program": p["program"][:55], "eligibility": p["eligibility"], "reason": "; ".join(p["reasons"] + p["checks"])[:120]} for p in r["programs"]])
""")
code(r"""
print("Upcoming admission deadlines on 2026-09-29:")
pd.DataFrame(advisor.upcoming_deadlines(kb, date(2026, 9, 29), audience="applicants"))[["date", "days_left", "institution", "title", "trust"]]
""")

md("## 4. Semester promotion engine (MUST rules, rule set `must.semester.v2017`)")
code(r"""
def c(code, pct, credits=3, att=None): return {"code": code, "credits": credits, "percent": pct, "attendance": att}
ok, fail = [c("A", 65), c("B", 70), c("C", 55), c("D", 60)], [c("A", 40), c("B", 45), c("C", 62), c("D", 30)]
cases = {
    "all passed":                     [ok, ok],
    "fail sem 1 -> probation":        [fail],
    "fail sem 1 and 2 -> dropped":    [fail, fail],
    "summer semester waives":         [{"courses": fail, "summer": [c("A", 60), c("B", 58)]}],
    "probation then fail sem 3":      [fail, ok, fail],
    "fail sem 4, fail sem 5 (reset)": [ok, ok, ok, fail, fail],
    "fail sem 5 and 6 -> relegated":  [ok, ok, ok, ok, fail, fail],
}
rows = []
for name, sems in cases.items():
    s = {"institution": "must", "program_type": "bs4",
         "semesters": [{"number": i + 1, **(x if isinstance(x, dict) else {"courses": x})} for i, x in enumerate(sems)]}
    ev = progression.evaluate(s)
    rows.append({"case": name, "outcomes": " -> ".join(f"S{o['semester']}:{o['outcome']}" + (f"(to {o['relegate_to']})" if o["relegate_to"] else "") for o in ev["semesters"]),
                 "status": ev["state"]["status"], "probations used": ev["state"]["probations_used"], "CGPA": ev["cgpa"]["gpa"]})
pd.DataFrame(rows)
""")
code(r"""
print("MUST's published worked examples:")
sem1 = [c("a", 52, 4), c("b", 70), c("c", 54, 2), c("d", 80, 1), c("e", 75)]
print(" semester example:", progression.gpa_report(sem1))
s = {"semesters": [{"number": 1, "courses": sem1}, {"number": 2, "courses": [c("f", 52, 4), c("g", 50), c("h", 50, 1)]}]}
print(" CGPA example    :", progression.gpa_report(progression.all_courses(s)))
""")

md("## 5. What-if simulation (student S-001 has pending semester-3 results and is on probation)")
code(r"""
s1 = store.get("students", "S-001")
last = progression.evaluate(s1)["semesters"][-1]
print("Pending:", last["pending"], "| passed", last["passed"], "of", last["opted"], "| need", last["required"])
rows = []
for scenario in [{"CS-301": 60, "CS-303": 62}, {"CS-301": 60, "CS-303": 40}, {"CS-301": 45, "CS-303": 45}]:
    w = progression.what_if(s1, scenario)["semesters"][-1]
    rows.append({"scenario": scenario, "outcome": w["outcome"], "relegate to": w["relegate_to"], "notes": " ".join(w["notes"])[:110]})
pd.DataFrame(rows)
""")

md("## 6. Proactive dashboards - every finding routed to an action")
code(r"""
def dash(sid):
    f = triage(monitor.scan(store.get("students", sid)), sid, record=False)
    return pd.DataFrame([{"action": x["action"], "finding": x["title"], "days left": x.get("days_left"), "detail": x["detail"][:100]} for x in f])

print("S-001 (MUST BS CS, on probation):"); display(dash("S-001"))
print("S-003 (UAJK, fee inside the 10% fine window):"); display(dash("S-003"))
print("S-002 (MUST final semester):"); display(dash("S-002"))
print("A-001 (applicant):"); display(dash("A-001"))
""")

md("## 7. Event-driven monitoring - paying the overdue hostel dues clears the alert")
code(r"""
s1 = store.get("students", "S-001")
before = {f["code"] for f in monitor.scan(s1)}
next(d for d in s1["dues"] if d["id"] == "D2").update(paid=True, paid_on="2026-09-29")
store.upsert("students", s1)
after = {f["code"] for f in monitor.scan(s1)}
print("removed:", before - after, "| added:", after - before)
""")

md("## 8. Application tracking - UAJK migration (submit within 15 days of paying the fee)")
code(r"""
app = applications.create("uajk.migration", "S-003")
print(app["id"], app["status"], "| fees:", [(f["item"], f["amount"]) for f in app["fees"]])
app = applications.update(app["id"], checklist_done=[0, 1, 2, 3], fee_paid_on="2026-09-20")
print("status:", app["status"], "| deadlines:", applications.deadlines_for(app))
""")

md("## 9. Chat pipeline - sample questions")
code(r"""
questions = [
    ("How do I get my degree from MUST?", None),
    ("what is the degree fee?", None),
    ("UAJK bonafide certificate", None),
    ("MUST transcript fee", None),
    ("mujhe MUST se clearance certificate kaise milega", None),
    ("UAJK duplicate degree lost degree", None),
    ("I did FSc pre-medical with 82%, matric 88%, MDCAT 71%, I want MBBS or DPT", None),
    ("ICS 64% which programs can I apply for in computing?", None),
    ("UAJK admission last date", None),
    ("Am I on probation? What happens if I fail again?", "S-001"),
    ("Can I get an extension for my fee deadline?", "S-003"),
    ("I am being harassed by a senior in hostel", "S-001"),
    ("MBBS degree from UHS", "S-004"),
]
rows = []
for q, sid in questions:
    r = assistant.answer(q, sid)
    rows.append({"question": q, "as": sid or "guest", "intent": r["intent"], "institution": r["institution"], "action": r["action"],
                 "first line": r["answer"].splitlines()[0][:80]})
pd.DataFrame(rows)
""")
code(r"""
display(Markdown(assistant.answer("I did FSc pre-medical with 82%, matric 88%, MDCAT 71%, I want MBBS or DPT")["answer"]))
""")

md("## 10. Evidence search and the human-advisor queue")
code(r"""
pd.DataFrame([{"score": round(s, 1), "kind": ch.kind, "trust": ch.trust, "source": ch.source, "text": ch.text[:90].replace("\n", " ")}
              for s, ch in kb.search("rechecking answer book fee days", k=6)])
""")
code(r"""
pd.DataFrame(store.load("escalations"))[["id", "student_id", "summary", "status"]]
""")

md("## 11. The MCP server, through the official MCP client (stdio)")
code(r"""
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def mcp_demo():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")],
                                   env={**os.environ, "JK_DISABLE_LLM": "1", "PYTHONIOENCODING": "utf-8"})
    # Jupyter's sys.stderr has no OS file handle, so send the server's stderr log to a real file
    with open(Path(os.environ["JK_DATA_DIR"]) / "mcp_server.log", "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                print("tools:", [t.name for t in (await s.list_tools()).tools])
                res = await s.call_tool("get_service", {"service_id": "uajk.english_proficiency"})
                card = json.loads(res.content[0].text)
                print(card["name"], "|", [(f["item"], f["amount"]) for f in card["fees"]], "|", card["processing_time"])

await mcp_demo()
""")

md("""
## 12. (Optional) Claude-written answer

With `ANTHROPIC_API_KEY` set before starting Jupyter, this cell calls `claude-opus-5-5`. Claude may only use the rule-engine result and the numbered evidence. Without a key it is skipped.
""")
code(r"""
if USE_CLAUDE:
    os.environ.pop("JK_DISABLE_LLM", None)
    r = assistant.answer("What documents do I need for a UAJK duplicate degree and how much does it cost?")
    display(Markdown(r["answer"]))
else:
    print("Skipped - set ANTHROPIC_API_KEY to see Claude-composed answers.")
""")

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
OUT.parent.mkdir(exist_ok=True)

if "--no-run" not in sys.argv:
    from nbclient import NotebookClient
    NotebookClient(nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(OUT.parent)}}).execute()
nbf.write(nb, OUT)
print(f"wrote {OUT}")
