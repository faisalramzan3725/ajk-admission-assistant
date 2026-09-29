"""Build (and optionally execute) notebooks/JK_Assistance_Samples.ipynb - admission samples.

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
# JK Assistance - admission samples

Sample students who have just finished 12th grade, run through the admission engine:

1. Entry tests: maximum and minimum marks (MDCAT out of 180, ECAT out of 400)
2. Eligibility checklists: required vs obtained, for sample students
3. MBBS merit aggregate (PM&DC formula 50 / 40 / 10)
4. Edge cases: below the minimum, test not yet taken, a failed ECAT with SEET still open, the Mathematics requirement, age limit
5. Step-by-step "how to apply" for UAJK, MUST and MBBS (the JAC website is down, so working channels are used)
6. Admission dates
7. The chat assistant on sample questions (English and Roman Urdu)
8. The MCP server, called through the official client

"Today" is fixed at **2026-09-29** so results are reproducible.
""")
code(r"""
import os, sys, json
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
os.environ["JK_TODAY"] = "2026-09-29"
USE_CLAUDE = bool(os.environ.get("ANTHROPIC_API_KEY"))
if not USE_CLAUDE:
    os.environ["JK_DISABLE_LLM"] = "1"
sys.path.insert(0, str(ROOT))
import pandas as pd
from IPython.display import Markdown, display
pd.set_option("display.max_colwidth", 80)
from jk_assistance import advisor, assistant
from jk_assistance.knowledge import get_knowledge
kb = get_knowledge()
print(f"{len(kb.programs)} programs, {len(kb.tests)} entry tests, {len(kb.dated_deadlines)} dated admission events, {len(kb.chunks)} evidence chunks")
""")

md("## 1. Entry tests - maximum and minimum marks")
code(r"""
rows = []
for tid, t in kb.tests.items():
    for k, v in (t.get("passing") or {}).items():
        if isinstance(v, dict):
            rows.append({"test": t["name"], "max marks": t.get("max_marks") or "on result card", "minimum for": k,
                         "min %": v["percent"], "min marks": v.get("marks") or (round(v["percent"] / 100 * t["max_marks"]) if t.get("max_marks") else "-")})
pd.DataFrame(rows)
""")

md("## 2. Eligibility checklists for sample students")
code(r"""
def show(profile, n=6):
    r = advisor.advise(profile)
    for p in r["programs"][:n]:
        print(f"\n{p['program'][:70]}  [{p['institution'].upper()}]  -> {p['eligibility']}  | chance: {p['chance']}")
        display(pd.DataFrame(p["checks"])[["criterion", "required", "yours", "status"]])
    return r

print("Sample A - FSc pre-medical 946/1100, matric 1010/1100, MDCAT 140/180, wants medicine")
r = show({"group": "pre_med", "hssc": "946/1100", "ssc": "1010/1100", "tests": {"mdcat": 140}, "state_subject": True, "interests": ["medicine"]}, n=3)
""")
code(r"""
print("Sample B - FSc pre-engineering 880/1100, ECAT 210/400, wants engineering")
r = show({"group": "pre_eng", "hssc": "880/1100", "tests": {"ecat": 210}, "interests": ["engineering"]}, n=3)
""")
code(r"""
print("Sample C - ICS 704/1100 (64%), no test yet, no interest given -> which fields are open?")
r = advisor.advise({"group": "ics", "hssc": "704/1100"})
display(pd.DataFrame(r["fields_open_to_you"]))
pd.DataFrame([{"program": p["program"][:60], "inst": p["institution"].upper(), "status": p["eligibility"], "chance": p["chance"],
               "1st sem fee": (p["fees"] or {}).get("first_semester")} for p in r["programs"] if p["eligibility"] != "not_eligible"])
""")

md("## 3. MBBS merit aggregate - PM&DC formula (MDCAT 50% + HSSC 40% + SSC 10%)")
code(r"""
rows = []
for mdcat in [99, 120, 140, 160, 175]:
    r = advisor.advise({"group": "pre_med", "hssc": "946/1100", "ssc": "1010/1100", "tests": {"mdcat": mdcat}, "state_subject": True, "interests": ["medicine"]})
    m = next(p for p in r["programs"] if p["id"] == "jac.mbbs")
    rows.append({"MDCAT": f"{mdcat}/180", "MDCAT %": round(mdcat / 180 * 100, 2), "eligible": m["eligibility"], "merit aggregate %": m["merit_aggregate"]})
pd.DataFrame(rows)
""")

md("## 4. Edge cases")
code(r"""
cases = [
    ("MDCAT 95/180 -> below 99 for MBBS, but >= 90 for BDS", {"group": "pre_med", "hssc": 80, "tests": {"mdcat": 95}, "state_subject": True, "interests": ["medicine", "dentistry"]}, ["jac.mbbs", "jac.bds"]),
    ("HSSC 58% -> below the 60% needed for MBBS", {"group": "pre_med", "hssc": 58, "tests": {"mdcat": 150}, "state_subject": True, "interests": ["medicine"]}, ["jac.mbbs"]),
    ("Pre-medical, MDCAT not taken yet", {"group": "pre_med", "hssc": 80, "state_subject": True, "interests": ["medicine"]}, ["jac.mbbs"]),
    ("ECAT 120/400 (< 132) but MUST SEET not taken yet", {"group": "pre_eng", "hssc": 80, "tests": {"ecat": 120}, "interests": ["engineering"]}, ["must.engineering"]),
    ("Pre-medical wants UAJK BS CS without Mathematics", {"group": "pre_med", "hssc": 80, "interests": ["computing"], "institutions": ["uajk"]}, ["uajk.bs_cs_ai"]),
    ("Same, with additional Mathematics", {"group": "pre_med", "hssc": 80, "interests": ["computing"], "institutions": ["uajk"], "studied_math": True}, ["uajk.bs_cs_ai"]),
    ("Age 25 at UAJK (limit 23)", {"group": "ics", "hssc": 70, "age": 25, "interests": ["computing"], "institutions": ["uajk"]}, ["uajk.bs_cs_ai"]),
    ("FA 55% wants engineering", {"group": "fa", "hssc": 55, "interests": ["engineering"]}, ["must.engineering"]),
]
rows = []
for name, prof, ids in cases:
    r = advisor.advise(prof)
    for pid in ids:
        p = next(x for x in r["programs"] if x["id"] == pid)
        rows.append({"case": name, "program": pid, "result": p["eligibility"],
                     "why": "; ".join(f"{c['criterion']}: {c['yours']} vs {c['required']}" for c in p["checks"] if c["status"] in ("fail", "pending"))[:110]})
pd.DataFrame(rows)
""")

md("## 5. How to apply - step by step")
code(r"""
display(Markdown("\n".join(assistant.render_howto(advisor.how_to_apply("uajk")))))
""")
code(r"""
display(Markdown("\n".join(assistant.render_howto(advisor.how_to_apply("jac")))))
""")

md("## 6. Admission dates (as of 2026-09-29)")
code(r"""
pd.DataFrame(advisor.upcoming_deadlines(kb, __import__("datetime").date(2026, 9, 29), include_past_days=20))[["date", "days_left", "institution", "title", "trust"]]
""")

md("## 7. The chat assistant on sample questions")
code(r"""
qs = ["I did FSc pre-medical 946/1100, matric 1010/1100, MDCAT 140/180, I want MBBS or DPT",
      "FSc pre-engineering 880/1100, ECAT 210 - engineering", "ICS 64% computer science", "MDCAT passing marks",
      "ECAT total marks", "How do I apply to UAJK?", "how to apply for MBBS in AJK", "UAJK last date",
      "mujhe MUST mein admission kaise milega", "I missed the deadline, can I still apply?", "How do I get my transcript?"]
pd.DataFrame([{"question": q, **{k: v for k, v in assistant.answer(q).items() if k in ("intent", "action", "institution")}} for q in qs])
""")
code(r"""
display(Markdown(assistant.answer("MDCAT passing marks")["answer"]))
""")

md("## 8. The MCP server, through the official MCP client")
code(r"""
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import tempfile

async def mcp_demo():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")],
                                   env={**os.environ, "JK_DISABLE_LLM": "1", "PYTHONIOENCODING": "utf-8"})
    with open(Path(tempfile.gettempdir()) / "jk_mcp_server.log", "w") as errlog:  # Jupyter's stderr has no OS handle
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                print("tools:", [t.name for t in (await s.list_tools()).tools])
                res = await s.call_tool("check_admission", {"group": "pre_med", "hssc_obtained": 946, "hssc_total": 1100,
                                                            "ssc_obtained": 1010, "ssc_total": 1100, "mdcat_obtained": 140, "interests": "medicine"})
                p = json.loads(res.content[0].text)["programs"][0]
                print(p["program"], "->", p["eligibility"], "| aggregate", p["merit_aggregate"])

await mcp_demo()
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
