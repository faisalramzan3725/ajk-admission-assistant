"""Build docs/JK_Assistance_Guide.pdf - manual, how it works, building an agent from scratch, and interview Q&A.

Usage: python scripts/build_guide_pdf.py
"""
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "JK_Assistance_Guide.pdf"
FONTS = Path("C:/Windows/Fonts")

# ---------------------------------------------------------------- fonts and styles
pdfmetrics.registerFont(TTFont("UI", str(FONTS / "segoeui.ttf")))
pdfmetrics.registerFont(TTFont("UI-B", str(FONTS / "segoeuib.ttf")))
pdfmetrics.registerFont(TTFont("UI-I", str(FONTS / "segoeuii.ttf")))
pdfmetrics.registerFont(TTFont("UI-BI", str(FONTS / "segoeuiz.ttf")))
pdfmetrics.registerFont(TTFont("UI-SB", str(FONTS / "seguisb.ttf")))
pdfmetrics.registerFont(TTFont("Mono", str(FONTS / "consola.ttf")))
pdfmetrics.registerFont(TTFont("Sym", str(FONTS / "seguisym.ttf")))  # glyphs Segoe UI lacks (⌂ ✕)
pdfmetrics.registerFont(TTFont("Mono-B", str(FONTS / "consolab.ttf")))
pdfmetrics.registerFontFamily("UI", normal="UI", bold="UI-B", italic="UI-I", boldItalic="UI-BI")
pdfmetrics.registerFontFamily("Mono", normal="Mono", bold="Mono-B", italic="Mono", boldItalic="Mono-B")

GREEN = colors.HexColor("#0f6b4f")
INK = colors.HexColor("#1c2420")
MUTED = colors.HexColor("#5d6a63")
LINE = colors.HexColor("#d9e0d9")
TINT = colors.HexColor("#eef4ef")
CODEBG = colors.HexColor("#f4f6f5")
AMBER = colors.HexColor("#8a6200")

ST = {
    "body": ParagraphStyle("body", fontName="UI", fontSize=10, leading=15, textColor=INK, spaceAfter=6),
    "small": ParagraphStyle("small", fontName="UI", fontSize=8.5, leading=12, textColor=MUTED),
    "h1": ParagraphStyle("h1", fontName="UI-B", fontSize=20, leading=25, textColor=GREEN, spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="UI-B", fontSize=13.5, leading=18, textColor=INK, spaceBefore=12, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="UI-SB", fontSize=11, leading=15, textColor=GREEN, spaceBefore=8, spaceAfter=3),
    "bullet": ParagraphStyle("bullet", fontName="UI", fontSize=10, leading=14.5, textColor=INK, leftIndent=14, bulletIndent=3, spaceAfter=2.5),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=8.3, leading=11.2, textColor=INK),
    "cell": ParagraphStyle("cell", fontName="UI", fontSize=8.8, leading=12, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="UI-B", fontSize=8.8, leading=12, textColor=INK),
    "q": ParagraphStyle("q", fontName="UI-B", fontSize=10.2, leading=14.5, textColor=GREEN, spaceBefore=7, spaceAfter=2),
    "a": ParagraphStyle("a", fontName="UI", fontSize=9.8, leading=14.2, textColor=INK, leftIndent=10, spaceAfter=3),
    "toc1": ParagraphStyle("toc1", fontName="UI-SB", fontSize=10.5, leading=17, leftIndent=0),
    "toc2": ParagraphStyle("toc2", fontName="UI", fontSize=9.5, leading=14, leftIndent=16, textColor=MUTED),
}


class Doc(SimpleDocTemplate):
    """Registers h1/h2 headings in the table of contents."""

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            level = 0 if f.style.name == "h1" else 1
            text = f.getPlainText()
            key = f"h{id(f)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
            self.notify("TOCEntry", (level, text, self.page, key))


story = []
H1 = lambda t: story.extend([PageBreak(), Paragraph(t, ST["h1"])])  # noqa: E731
H2 = lambda t: story.extend([CondPageBreak(60 * mm), Paragraph(t, ST["h2"])])  # noqa: E731
H3 = lambda t: story.append(Paragraph(t, ST["h3"]))  # noqa: E731
P = lambda t: story.append(Paragraph(t, ST["body"]))  # noqa: E731
SP = lambda h=6: story.append(Spacer(1, h))  # noqa: E731


def BL(items):
    for it in items:
        story.append(Paragraph(it, ST["bullet"], bulletText="•"))
    SP(3)


def NL(items):
    for i, it in enumerate(items, 1):
        story.append(Paragraph(it, ST["bullet"], bulletText=f"{i}."))
    SP(3)


def CODE(text):
    pre = Preformatted(text.strip("\n"), ST["code"])
    t = Table([[pre]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CODEBG), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.extend([t, Spacer(1, 8)])


def TABLE(rows, widths, header=True):
    data = [[Paragraph(str(c), ST["cellb"] if (header and r == 0) else ST["cell"]) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), TINT))
    t.setStyle(TableStyle(style))
    story.extend([t, Spacer(1, 9)])


def BOX(title, text, color=GREEN):
    inner = [Paragraph(f"<b>{title}</b>", ParagraphStyle("bt", parent=ST["body"], textColor=color, spaceAfter=2)),
             Paragraph(text, ParagraphStyle("bx", parent=ST["body"], spaceAfter=0))]
    t = Table([[inner]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.extend([t, Spacer(1, 9)])


def QA(q, a):
    story.append(KeepTogether([Paragraph(q, ST["q"]), Paragraph(a, ST["a"])]))


def flow_diagram(steps, width=170 * mm, box_h=15 * mm, gap=5 * mm, title=None):
    """Vertical pipeline of boxes with arrows."""
    n = len(steps)
    h = n * box_h + (n - 1) * gap + (8 * mm if title else 2 * mm)
    d = Drawing(width, h)
    y = h - (8 * mm if title else 2 * mm)
    if title:
        d.add(String(0, h - 5 * mm, title, fontName="UI-SB", fontSize=9.5, fillColor=MUTED))
    for i, (head, sub) in enumerate(steps):
        top = y - i * (box_h + gap)
        d.add(Rect(0, top - box_h, width, box_h, rx=6, ry=6, fillColor=TINT if i % 2 == 0 else colors.white, strokeColor=GREEN, strokeWidth=0.8))
        d.add(String(8, top - 6.2 * mm, head, fontName="UI-B", fontSize=10, fillColor=GREEN))
        d.add(String(8, top - 11.4 * mm, sub, fontName="UI", fontSize=8.4, fillColor=INK))
        if i < n - 1:
            cx, y1, y2 = width / 2, top - box_h, top - box_h - gap
            d.add(Line(cx, y1, cx, y2 + 1.6 * mm, strokeColor=GREEN, strokeWidth=1.2))
            d.add(Polygon([cx - 2.2 * mm, y2 + 2 * mm, cx + 2.2 * mm, y2 + 2 * mm, cx, y2], fillColor=GREEN, strokeColor=GREEN))
    story.extend([d, Spacer(1, 10)])


def on_page(canv, doc):
    if doc.page == 1:
        return
    canv.saveState()
    canv.setFont("UI", 8)
    canv.setFillColor(MUTED)
    canv.drawString(20 * mm, 12 * mm, "JK Assistance - manual, how it works, building an agent, interview preparation")
    canv.drawRightString(190 * mm, 12 * mm, f"Page {doc.page}")
    canv.setStrokeColor(LINE)
    canv.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canv.restoreState()


# ================================================================ COVER
story += [Spacer(1, 45 * mm),
          Paragraph("JK Assistance", ParagraphStyle("t", fontName="UI-B", fontSize=34, leading=40, textColor=GREEN, alignment=TA_CENTER)),
          Spacer(1, 4 * mm),
          Paragraph("An admission assistant for students in Azad Jammu &amp; Kashmir",
                    ParagraphStyle("st", fontName="UI", fontSize=14, leading=19, textColor=INK, alignment=TA_CENTER)),
          Spacer(1, 14 * mm),
          Paragraph("Manual  ·  How it works  ·  Building an agent from scratch  ·  Interview questions and answers",
                    ParagraphStyle("st2", fontName="UI-SB", fontSize=11, leading=16, textColor=MUTED, alignment=TA_CENTER)),
          Spacer(1, 10 * mm),
          Paragraph("A beginner-friendly guide", ParagraphStyle("st3", fontName="UI-I", fontSize=11, leading=16, textColor=MUTED, alignment=TA_CENTER)),
          Spacer(1, 60 * mm),
          Paragraph("Author: Faisal Ramzan  ·  Repository: github.com/faisalramzan3725/ajk-admission-assistant (private)  ·  Version: September 2026",
                    ParagraphStyle("st4", fontName="UI", fontSize=8.5, leading=12, textColor=MUTED, alignment=TA_CENTER))]

# ================================================================ CONTENTS
story.append(PageBreak())
story.append(Paragraph("Contents", ParagraphStyle("contents", parent=ST["h1"])))
toc = TableOfContents()
toc.levelStyles = [ST["toc1"], ST["toc2"]]
toc.dotsMinLevel = 0
story.append(toc)

# ================================================================ PART 1
H1("1. What JK Assistance is")
P("Every year thousands of students in Azad Jammu &amp; Kashmir (AJK) finish their intermediate (12 years of education) and face the same "
  "questions: <i>Which programs can I apply for with my group and marks? What MDCAT or ECAT score do I need? Which documents do I prepare? "
  "Where do I apply, and by when?</i> The official answers are spread across many university websites, scanned PDFs and notices - and one "
  "key admission site (the Joint Admission Committee portal for MBBS/BDS) does not even open.")
P("<b>JK Assistance</b> puts all of this in one place. A student enters their group and marks; the assistant shows every program they can "
  "apply to, checks each requirement against their own marks, calculates the MBBS/BDS merit aggregate, lists the documents and fees, "
  "explains how to apply step by step, and shows the admission dates with links.")
H2("Who it helps")
BL(["Students who have just finished FSc (pre-medical or pre-engineering), ICS, FA, I.Com, DAE or A-level and have not decided where to go.",
    "Parents and teachers who guide them.",
    "Admission offices, as a single place where students can find correct, sourced information."])
H2("What it covers")
TABLE([["Area", "Details"],
       ["Institutions", "University of AJK (UAJK, Muzaffarabad), Mirpur University of Science &amp; Technology (MUST), the AJK public medical "
        "colleges (AJKMC, MBBSMC, Poonch Medical College) and SZABMU federal medical colleges with AJK-quota seats."],
       ["Programs", "40 program groups: engineering, computing, medicine, dentistry, health sciences, natural and social sciences, business, law, education, arts."],
       ["Entry tests", "MDCAT (out of 180; MBBS needs 99, BDS 90), ECAT (out of 400; PEC engineering needs 132), MUST SEET (33%), UAJK entry test (50%), HEC LAT (50%)."],
       ["Dates", "Last dates, merit lists and MDCAT schedule, each with a clickable link to where the student acts."],
       ["Languages", "Questions in English or Roman Urdu."]], [32, 138])
BOX("A quick example",
    "A student types: <i>\"I did FSc pre-medical 946/1100, matric 1010/1100, MDCAT 140/180 - I want MBBS or DPT.\"</i><br/>"
    "JK Assistance answers: <b>MBBS at the AJK public colleges - Eligible.</b> HSSC needs ≥ 60%, you have 86% (pass). MDCAT needs "
    "≥ 55% = 99 / 180, you have 140 / 180 = 77.78% (pass). Merit aggregate = 0.5 × 77.78 + 0.4 × 86 + 0.1 × 91.82 = <b>82.472%</b>. "
    "Then it lists DPT options, the documents, the steps to apply and the upcoming dates.")

# ================================================================ PART 2
H1("2. How it works")
P("The most important idea: <b>the rules decide, the AI only explains.</b> Eligibility, marks, fees and dates are computed by ordinary code "
  "from carefully checked data. A large language model (Claude) is used only to phrase the answer nicely - and only when an API key is "
  "configured. This makes every answer correct, repeatable and traceable to an official source.")
flow_diagram([
    ("1. Official sources", "University websites, PM&DC notices, prospectuses, scanned fee sheets (saved in raw/ and documents/)"),
    ("2. Knowledge files (YAML)", "Checked facts: programs, minimum marks, tests (max/min), fees, steps, dates, each with its source"),
    ("3. Eligibility engine", "Compares the student's marks with every program's rules: pass / fail / pending / check"),
    ("4. Chat router + decision", "Understands the question; decides GUIDE, ASK_INFO, ALERT, ESCALATE or OFF_TOPIC"),
    ("5. Evidence search (BM25)", "Finds the official text behind the answer (1,450 indexed chunks)"),
    ("6. Answer", "Claude writes from the result + evidence, or the built-in renderer formats it"),
    ("7. Interfaces", "Web portal, REST API, MCP tools for Claude Desktop / Claude Code"),
], title="From official websites to a student's answer")
H2("The building blocks")
TABLE([["Block", "File", "What it does (in simple words)"],
       ["Knowledge", "knowledge/*.yaml", "The 'rule book': every program's accepted groups and minimum marks, every test's maximum and passing marks, fees, steps and dates - each with its source link."],
       ["Knowledge loader", "jk_assistance/knowledge.py", "Reads the rule book and builds a search index over all official pages and documents."],
       ["Eligibility engine", "jk_assistance/advisor.py", "Converts marks to percentages, checks each requirement, gives a verdict, computes the merit aggregate and a chance estimate."],
       ["Chat router", "jk_assistance/assistant.py", "Reads a free-text question, pulls out group and marks, and picks the right engine."],
       ["Decision layer", "jk_assistance/decision.py", "Stops unsafe or unanswerable cases: sensitive topics and exceptions go to the admission office."],
       ["LLM composer", "jk_assistance/llm.py", "Optional: asks Claude to write the answer using only the engine result and numbered evidence."],
       ["API + portal", "jk_assistance/api.py, web/index.html", "The website students use, and endpoints for other programs."],
       ["MCP server", "mcp_server/server.py", "Lets AI assistants (Claude Desktop, Claude Code) use JK Assistance as tools."],
       ["Update agent", "scripts/update_agent.py", "Checks the 23 official sources daily and reports changes for a person to verify."]], [30, 45, 95])
H2("How eligibility is checked")
P("For each program the engine builds a small checklist. Each row has a <b>requirement</b>, what is <b>needed</b>, what the student <b>has</b>, and a <b>status</b>:")
TABLE([["Requirement", "Needed", "You", "Status"],
       ["Intermediate group", "F.Sc. Pre-Medical", "F.Sc. Pre-Medical", "pass"],
       ["HSSC marks", "≥ 60%", "86%", "pass"],
       ["MDCAT", "≥ 55% = 99 / 180", "140 / 180 = 77.78%", "pass"],
       ["AJK State Subject", "required for AJK-national seats", "yes", "pass"]], [45, 50, 50, 25])
P("Then it gives one of four verdicts:")
BL(["<b>Eligible</b> - every requirement passes.",
    "<b>Eligible if you pass the test</b> - only an entry test is still missing (the student has not taken it yet). The engine never rejects a student just because a test is not taken.",
    "<b>Check with the office</b> - a rule is not published (for example BS Nursing minimum marks).",
    "<b>Not eligible</b> - a requirement fails, and the reason is shown (for example \"HSSC 58% vs ≥ 60%\")."])
P("Some programs accept <b>any one</b> of several tests. MUST engineering accepts its own SEET <i>or</i> another PEC-approved test such as ECAT. "
  "If a student's ECAT is below 132/400 but they have not taken SEET yet, they are still \"eligible if you pass the test\".")
H2("The merit aggregate and the chance label")
P("For MBBS/BDS the official PM&amp;DC formula is used: <b>MDCAT 50% + HSSC 40% + SSC 10%</b>. For other programs no university publishes "
  "closing merits, so the <b>chance</b> label is a clearly marked <i>heuristic</i>: it looks at how far the student is above the minimum and "
  "how competitive the program is. For ECAT programs it compares the score with UET's official average for the student's group (for "
  "example 203/400 for pre-engineering in Fall 2026).")
H2("How the chat understands a question")
TABLE([["Student asks", "The assistant decides", "Result"],
       ["\"FSc pre-engineering 880/1100, ECAT 210 - engineering\"", "Marks are given -&gt; admission advice", "Programs with checklists"],
       ["\"MDCAT passing marks\"", "A test is named, no marks -&gt; test information", "Max 180, MBBS 99, BDS 90, format, fee"],
       ["\"How to apply for MBBS in AJK\"", "Steps question + medicine -&gt; how to apply", "Steps, documents, working contacts"],
       ["\"UAJK last date\"", "Date question -&gt; deadlines", "Dates with links (ALERT if close)"],
       ["\"I missed the deadline, can I still apply?\"", "Exception -&gt; ESCALATE", "Contact the admission office"],
       ["\"How do I get my transcript?\"", "Not about admission -&gt; OFF_TOPIC", "Polite redirect"]], [58, 62, 50])
H2("Keeping the information fresh: the update agent")
P("Admission dates and fees change every year. The <b>update agent</b> runs every day (through GitHub Actions) and, for each of the 23 "
  "official sources, it: fetches the page, compares it with yesterday's copy, looks for new dates, fees, rule sentences and new PDF "
  "notices, checks that every link shown to students still works, and flags when the calendar needs the next admission cycle. When "
  "something changed it opens a <b>pull request</b> with a report. A person checks the official source and approves the change. The "
  "agent never edits the rules by itself, because fees, dates and minimum marks are official facts.")
BOX("Why a human approves", "An AI or a script can misread a notice. By letting the agent <i>find and highlight</i> changes but letting a "
    "person <i>confirm</i> them, every answer a student sees stays traceable to a verified official source.")
H2("Dealing with a broken official website")
P("The JAC admission portal (jac.ajk.gov.pk) returns an error. Instead of sending students to a dead link, JK Assistance marks it as "
  "not working and points to working official channels: PM&amp;DC (the regulator), SZABMU Islamabad (which conducts MDCAT for AJK and "
  "runs federal colleges with AJK-quota seats) and the admission cells of Poonch Medical College and MBBS Medical College Mirpur. The update agent reports when the JAC site comes back.")

# ================================================================ PART 3
H1("3. User manual")
H2("Install and run")
NL(["Install Python 3.11 or newer.",
    "Open a terminal in the project folder and install the libraries: <font name='Mono'>pip install -r requirements.txt</font>",
    "Start the server: <font name='Mono'>python -m uvicorn jk_assistance.api:app --port 8010</font>",
    "Open <b>http://localhost:8010</b> in a browser. API documentation is at <b>http://localhost:8010/docs</b>."])
BOX("If the port is busy", "The error <i>[Errno 10048] ... 8010</i> means another program already uses port 8010. Stop it, or start on "
    "another port with <font name='Mono'>--port 8011</font>.", AMBER)
P("<b>Optional:</b> copy <font name='Mono'>.env.example</font> to <font name='Mono'>.env</font> and set <font name='Mono'>ANTHROPIC_API_KEY</font> "
  "to let Claude write the chat answers. Without it everything still works; answers are formatted by the built-in renderer.")
H2("The portal, screen by screen")
TABLE([["Screen", "What the student does"],
       ["1. Find my programs", "Choose the intermediate group; enter HSSC and SSC marks as <i>obtained / out of</i>; enter test scores if taken (MDCAT out of 180, ECAT out of 400, UAJK test, SEET, LAT); optionally choose an interest, a university, age, State Subject and Mathematics. Press <b>Check my eligibility</b>."],
       ["Results", "A summary (how many programs are open, the next deadline), then one card per program with the needed-vs-yours table, the verdict, chance, fees and seats, and the steps to apply. Buttons: <b>Edit my marks</b>, <b>Start over</b>, <b>Next: how to apply</b>."],
       ["2. How to apply", "Steps, a tickable document checklist, dates, age limit, reserved seats, scholarships, fee rules and contacts for UAJK, MUST and MBBS/BDS."],
       ["Entry tests", "One card per test: total marks, minimum marks, format, fee and dates."],
       ["Admission dates", "Upcoming dates first. Each title is a link, with a <b>Go</b> button (portal, merit lists) and a link to the official notice."],
       ["Ask a question", "Chat in English or Roman Urdu, with the sources used."]], [38, 132])
H2("Navigation")
BL(["<b>← Back</b> returns to the previous screen (the browser's back button and Alt+← also work, and results are kept).",
    "<b><font name='Sym'>⌂</font> Home</b> goes to \"Find my programs\".",
    "<b><font name='Sym'>✕</font> Clear</b> empties the current screen: marks and results, the conversation, or the checklist.",
    "Each screen has its own address, e.g. <font name='Mono'>/#dates</font>, which can be shared or bookmarked."])
H2("Example questions to try")
BL(["I did FSc pre-medical 946/1100, matric 1010/1100, MDCAT 140/180 - I want MBBS or DPT",
    "FSc pre-engineering 880/1100, ECAT 210 - engineering",
    "ICS 64% computer science",
    "MDCAT passing marks  ·  ECAT total marks",
    "How do I apply to UAJK?  ·  mujhe MUST mein admission kaise milega",
    "UAJK last date"])
H2("For developers: API, MCP and tests")
TABLE([["What", "How"],
       ["Eligibility API", "POST /api/advise with group, hssc, ssc, tests, interests ... (see the /docs page)"],
       ["Other endpoints", "/api/tests, /api/how-to-apply/{uajk|must|jac}, /api/deadlines, /api/programs, /api/search, /api/chat, /api/health"],
       ["MCP server", "python mcp_server/server.py  (tools: check_admission, get_test, how_to_apply, admission_dates, list_programs, search_admission_sources, ask_jk_assistance)"],
       ["Tests", "python -m pytest -q  (49 tests)"],
       ["Sample notebook", "notebooks/JK_Assistance_Samples.ipynb - rebuild with python scripts/build_notebook.py"],
       ["Update agent", "python scripts/update_agent.py --no-llm  (report in reports/update_report.md)"]], [35, 135])
H2("Updating the information")
NL(["Read the update agent's report (or the pull request it opened).",
    "Open the official source link and confirm the change.",
    "Edit <font name='Mono'>knowledge/deadlines.yaml</font> (dates) or <font name='Mono'>knowledge/admissions.yaml</font> (programs, tests, fees, steps). Always include the source link.",
    "Run <font name='Mono'>python -m pytest -q</font>, check the portal, and merge."])

# ================================================================ PART 4
H1("4. Building an agent from scratch (beginner tutorial)")
P("This part explains, step by step, how to build an assistant like JK Assistance even if you are new to AI. The same recipe works for "
  "other domains: scholarship finders, visa guides, hospital help desks, HR policy assistants.")
H2("First, the key ideas in plain words")
TABLE([["Term", "Meaning"],
       ["LLM (large language model)", "A model such as Claude that reads and writes text. Very good at language, but it can invent facts if not grounded."],
       ["Grounding", "Giving the model the exact facts to use, so it does not guess."],
       ["RAG (retrieval-augmented generation)", "Search your own documents first, then give the found text to the model to answer from."],
       ["Rule engine", "Ordinary code with if/else rules. Perfect for facts like \"HSSC ≥ 60%\"."],
       ["Agent", "A program that observes, decides and acts towards a goal, often in a loop, using tools. JK Assistance's update agent watches websites, decides what changed and acts by reporting it."],
       ["Tool / MCP", "A function an AI can call. MCP (Model Context Protocol) is a standard way to offer tools to AI apps."],
       ["Human in the loop", "A person approves important actions (here: changes to official dates and fees)."]], [45, 125])
H2("Step 1 - Define the goal and the user")
P("Write one sentence: <i>\"Help a student who has finished 12th grade in AJK decide where to apply, check eligibility and follow the steps.\"</i> "
  "List the questions users really ask. Decide what the assistant must <b>not</b> do (here: invent cut-off marks, answer non-admission topics, send people to dead links).")
H2("Step 2 - Collect the official sources")
P("Download every official page and document, and record where each came from. Keep the raw copies; they are your evidence.")
CODE('''
import requests, bs4
def fetch(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    soup = bs4.BeautifulSoup(r.text, "lxml")
    for t in soup(["script", "style", "nav", "footer"]):
        t.decompose()                        # remove menus and scripts
    return soup.get_text("\\n", strip=True)  # clean page text
''')
H2("Step 3 - Turn facts into structured data")
P("Do not leave important facts inside long text. Put them in a clear format (YAML or JSON) that code can use, with the source next to each fact.")
CODE('''
tests:
  mdcat:
    max_marks: 180
    passing:
      mbbs: {percent: 55, marks: 99}
      bds:  {percent: 50, marks: 90}
    merit_formula: {mdcat: 50, hssc: 40, ssc: 10}
    sources: ["https://pmdc.pk/Documents/law/Admissions Regulations-2025.pdf"]
programs:
  - {id: jac.mbbs, groups: [pre_med, a_level], min_percent: 60,
     test_rules: [{test: mdcat, min_percent: 55}]}
''')
H2("Step 4 - Write the rule engine")
P("Use plain code for decisions that must be exactly right. Show the student both what is needed and what they have.")
CODE('''
def check_program(prog, student):
    rows = []
    rows.append(("HSSC", f">= {prog['min_percent']}%", student["hssc"],
                 student["hssc"] >= prog["min_percent"]))
    for rule in prog["test_rules"]:
        score = student["tests"].get(rule["test"])          # None = not taken yet
        ok = None if score is None else score >= rule["min_percent"]
        rows.append((rule["test"], f">= {rule['min_percent']}%", score, ok))
    if any(ok is False for *_, ok in rows):  return "not eligible", rows
    if any(ok is None for *_, ok in rows):   return "eligible if you pass the test", rows
    return "eligible", rows
''')
H2("Step 5 - Add search over your documents (retrieval)")
P("Split documents into chunks and index them. BM25 is a simple, fast keyword ranking method and a good first choice; vector embeddings can be added later.")
CODE('''
from rank_bm25 import BM25Okapi
chunks = [...]                                     # pieces of official text
index = BM25Okapi([c.lower().split() for c in chunks])
scores = index.get_scores("mdcat passing marks".split())
top = sorted(zip(scores, chunks), reverse=True)[:6]  # evidence for the answer
''')
H2("Step 6 - Understand the question (router) and decide the action")
P("Pull the useful details from the question (group, marks, test names), then route it: advice, test info, how to apply, dates - or stop "
  "early when a person must decide (exceptions, sensitive topics) or when the question is out of scope.")
CODE('''
import re
def route(q):
    if re.search(r"harass|missed the deadline|extension|appeal", q, re.I): return "ESCALATE"
    if re.search(r"transcript|cgpa|degree issue", q, re.I):             return "OFF_TOPIC"
    if re.search(r"\\d+\\s*/\\s*\\d+|\\d+\\s*%", q):                          return "ADVICE"
    if re.search(r"mdcat|ecat", q, re.I):                               return "TEST_INFO"
    if re.search(r"last date|deadline", q, re.I):                       return "DATES"
    return "HOW_TO_APPLY"
''')
H2("Step 7 - Let the LLM write the answer (grounded)")
P("Give Claude the engine's result and the evidence, and tell it clearly not to invent anything. If the call fails, fall back to your own formatted answer so the system always works.")
CODE('''
import anthropic, json
SYSTEM = ("You are an admission assistant. Use ONLY the RESULT and EVIDENCE. "
          "Never invent marks, fees or dates. Cite evidence as [1], [2].")
def compose(question, result, evidence):
    client = anthropic.Anthropic()                   # reads ANTHROPIC_API_KEY
    resp = client.messages.create(
        model="claude-opus-5-5", max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content":
                   f"QUESTION: {question}\\nRESULT: {json.dumps(result)}\\nEVIDENCE: {evidence}"}])
    return "".join(b.text for b in resp.content if b.type == "text")
''')
H2("Step 8 - Build the interfaces")
BL(["<b>Web portal</b> for students (a form with labelled inputs, results cards, dates with links).",
    "<b>REST API</b> (FastAPI) so other apps can use the engine.",
    "<b>MCP server</b> so AI assistants can call your functions as tools."])
CODE('''
from fastapi import FastAPI
app = FastAPI()
@app.post("/api/advise")
def advise(profile: dict):
    return check_all_programs(profile)          # the rule engine from Step 4
''')
H2("Step 9 - Test everything")
P("Write a test for every rule and edge case: below the minimum, test not taken, the \"any one test\" rule, wrong group, age limit, and "
  "for the chat, that each sample question goes to the right place. Tests protect you when data or code changes.")
CODE('''
def test_mdcat_below_99_fails_mbbs():
    r = advise({"group": "pre_med", "hssc": 80, "tests": {"mdcat": 95}})
    assert status(r, "jac.mbbs") == "not_eligible"
''')
H2("Step 10 - Make it an agent that keeps itself up to date")
P("The update agent follows a classic agent loop: <b>observe → compare → decide → act → report</b>, then waits for the next run.")
flow_diagram([
    ("Observe", "Fetch the 23 official sources (and note which sites are down)"),
    ("Compare", "Diff today's text with the last saved copy"),
    ("Decide", "New dates? fees? rule sentences? new PDFs? broken links? empty calendar?"),
    ("Act", "Save the fresh text; optionally ask Claude to draft date entries as validated JSON"),
    ("Report", "Write a report and open a pull request for a person to approve"),
], box_h=13 * mm, gap=4 * mm)
H2("Step 11 - Guardrails and lessons learned")
BL(["Never let the model invent official numbers - compute them.",
    "Record the source and a trust level for every fact; label third-party information \"verify\".",
    "Handle broken websites honestly and give working alternatives.",
    "Ask for missing information instead of guessing (ASK_INFO).",
    "Send exceptions and sensitive cases to people (ESCALATE).",
    "Keep a human approval step for changes to official facts.",
    "Watch out for small data traps: \"MUST\" is also an English word; \"pre-medical\" is a group, not an interest; MDCAT 95 means 95/180, not 95%."])

# ================================================================ PART 5
H1("5. Interview preparation")
P("This part helps you present JK Assistance in a job or scholarship interview. Answers are written in simple language; adapt them to your own words.")
H2("Your 60-second pitch")
BOX("Say this when asked \"Tell me about your project\"",
    "\"Students in Azad Kashmir who finish intermediate often don't know where they can apply or what marks they need, because the "
    "information is spread across many websites and scanned PDFs, and one official admission portal doesn't even work. I built JK "
    "Assistance, an admission assistant that turns official sources into a checked rule book. A student enters their group and marks, and "
    "it shows every program they can apply to, with each requirement as needed versus their own marks - for example MDCAT 99 out of 180 "
    "versus their 140 - plus the MBBS merit aggregate, documents, fees, steps and dates with links. The key design choice is that rules "
    "decide and the AI only explains, so answers are exact and traceable. A daily agent watches 23 official sources and opens a pull "
    "request when something changes, and a person approves it. It has a web portal, an API, MCP tools and 49 automated tests.\"")
H2("A. Questions about the project")
QA("Q1. What problem does your project solve?",
   "Students after 12th grade in AJK lack one reliable place to learn which programs they can join, what test scores they need and how to "
   "apply. JK Assistance gives a personalised answer from official sources in seconds, including marks comparisons, documents, fees and dates.")
QA("Q2. Who are the users, and how did you decide what to build?",
   "Students who haven't decided where to go, plus parents and teachers. I listed the questions they actually ask - eligibility, test "
   "marks, documents, deadlines - and built one feature for each. I also narrowed the scope to admissions only so the tool stays focused and reliable.")
QA("Q3. Walk me through what happens when a student checks eligibility.",
   "Their marks are converted to percentages (for example 946/1100 = 86%). For each of the 40 programs the engine checks the group, the "
   "minimum HSSC, Mathematics if required, the entry test, age and State Subject. Each check becomes a row of needed versus theirs with "
   "pass, fail, pending or check. The rows give a verdict, the MBBS aggregate is computed with the PM&amp;DC formula, and the results are ranked by the student's interests.")
QA("Q4. Where does the data come from, and how do you know it's correct?",
   "From official websites and documents: UAJK, MUST, PM&amp;DC notices and regulations, SZABMU, the medical colleges. I saved the raw "
   "copies, extracted the text, read scanned PDFs manually, and stored each fact with its source link and a trust level. Third-party "
   "facts are marked 'verify'. Tests check that the data files are consistent.")
QA("Q5. What was the hardest part?",
   "Messy, unreliable sources. Some fee sheets were scanned images, some pages only render with JavaScript, the JAC portal is blocked, and "
   "even a similarly named website (pmc.edu.pk) belonged to a different college. I handled each case explicitly: manual transcription, a "
   "real browser capture, working alternative channels, and verification of every domain.")
QA("Q6. What would you improve next?",
   "Add the next admission cycle's dates as they are announced, transcribe the remaining scanned fee sheets, add Urdu-script answers, and, if "
   "universities publish closing merits, replace the heuristic chance with a real comparison.")
H2("B. Questions about AI, LLMs and RAG")
QA("Q7. Why didn't you let the AI answer everything directly?",
   "LLMs can produce confident but wrong numbers. Admission decisions depend on exact values like 99 out of 180, so the numbers are "
   "computed by code from verified data. The model only turns the result into friendly language, and it must cite the evidence.")
QA("Q8. What is RAG and how did you use it?",
   "Retrieval-augmented generation means searching your own documents first and giving the found text to the model. I split the official "
   "pages and documents into about 1,450 chunks and used BM25 keyword search to find the six most relevant pieces for each question.")
QA("Q9. Why BM25 and not vector embeddings?",
   "The questions contain precise words like MDCAT, ECAT, 'last date' and program names, which keyword search handles very well. BM25 is fast, "
   "needs no extra model and is easy to explain. Retrieval only supplies evidence; the main answers come from structured data. Embeddings are a possible later upgrade.")
QA("Q10. How do you prevent hallucinations?",
   "Four ways: the facts come from the rule engine, not the model; the system prompt forbids inventing numbers and requires citations; "
   "if the model call fails or refuses, a deterministic answer is shown; and questions outside the scope are redirected instead of answered.")
QA("Q11. What happens if there is no API key or the AI service is down?",
   "Everything still works. The engine's result is formatted by a built-in renderer. The AI only improves the wording.")
QA("Q12. How does the assistant handle questions it shouldn't answer?",
   "A decision layer labels them. Exceptions such as missed deadlines or appeals, and sensitive topics, are ESCALATE - the student gets the "
   "admission office contacts. Non-admission topics are OFF_TOPIC. Missing details trigger ASK_INFO.")
H2("C. Questions about agents")
QA("Q13. What is an AI agent? Is your project an agent?",
   "An agent observes its environment, decides and acts towards a goal, usually in a loop, using tools. The update agent is one: every day "
   "it observes 23 websites, compares them with the last copy, decides what is new or broken, acts by saving the text and drafting "
   "updates, and reports through a pull request.")
QA("Q14. Why doesn't the agent update the data automatically?",
   "Because fees, dates and minimum marks are official facts. A misread notice could mislead thousands of students. The agent finds and "
   "highlights the change; a person verifies it and approves. That is the 'human in the loop' principle.")
QA("Q15. What is MCP and why did you add it?",
   "The Model Context Protocol is a standard for giving AI assistants tools. My MCP server exposes functions such as check_admission and "
   "get_test, so an assistant like Claude Desktop can answer admission questions using my verified engine rather than guessing.")
H2("D. Questions about engineering and testing")
QA("Q16. How did you test the system?",
   "With 49 automated tests covering mark parsing, each eligibility rule and edge case, the merit aggregate, chat routing, the API and the "
   "update agent's detectors. I also ran sample notebooks, tested the portal in a browser, and simulated a changed web page to prove the agent detects new dates.")
QA("Q17. Give an example of a bug you found and fixed.",
   "MDCAT 95 was first read as 95 percent instead of 95 out of 180, which would have marked a failing student as eligible for MBBS. A "
   "test caught it, and I changed the rule so that for tests with a fixed maximum a plain number means marks obtained. Another: 'must' is "
   "an English word, so 'which documents must I attach' was treated as MUST university; now only the uppercase acronym counts.")
QA("Q18. How is the project structured?",
   "Data (raw sources and YAML rule files) is separate from logic (engine, router, decision layer) and from interfaces (portal, API, MCP). "
   "This separation means data can be updated without touching code, and each part can be tested on its own.")
QA("Q19. How do you handle a website that is down?",
   "The JAC portal returns a block page. I do not bypass protections; I mark the site as not working, give students working official "
   "alternatives, never link to it, and the update agent reports when it comes back.")
H2("E. Questions about ethics and limits")
QA("Q20. What are the limitations of your system?",
   "The chance label is a heuristic, because closing merits are not published. Some scanned fee sheets are not yet transcribed. The JAC "
   "and AJKMC websites are unavailable. And the data must be refreshed every admission cycle, which the agent helps with.")
QA("Q21. How do you deal with personal data?",
   "The eligibility check needs only marks and group, nothing that identifies the student, and nothing is stored. When I found an official "
   "statistics file that listed candidates' names, I kept only the averages and deleted the file.")
QA("Q22. Could this give wrong advice? What protects students?",
   "Every requirement is shown with its source, third-party facts are labelled, exceptions go to the admission office, and students are "
   "told to confirm final details with the institution. Human approval of data changes adds another safety layer.")
H2("F. General and behavioural questions")
QA("Q23. What did you learn from this project?",
   "That reliable AI products are mostly about good data and clear rules. The model is a small part; knowing when not to use it, how to show "
   "evidence and how to keep information current matters more.")
QA("Q24. How would you explain your project to a non-technical person?",
   "\"It's like a knowledgeable counsellor who has read every university's admission rules. You tell it your marks, and it tells you where you "
   "can apply, what you still need and when to apply - and shows you the official page for each answer.\"")
QA("Q25. How did you manage your time and priorities?",
   "I started with the most common student need - 'Where can I apply with my marks?' - then added tests, steps and dates, then reliability "
   "work (tests, the update agent). When the scope grew, I cut features that did not serve admissions.")
H2("Tips for answering well")
BL(["Use the <b>STAR</b> method for behavioural questions: Situation, Task, Action, Result.",
    "Always mention one concrete number: 40 programs, 23 sources, 49 tests, MDCAT 99/180.",
    "Be honest about limitations - interviewers value it.",
    "Prepare a short live demo: one eligibility check and one chat question.",
    "Practise the 60-second pitch aloud until it feels natural."])

# ================================================================ GLOSSARY
H1("6. Glossary")
TABLE([["Term", "Meaning"],
       ["HSSC / SSC", "Higher Secondary School Certificate (intermediate, 12 years) / Secondary School Certificate (matric, 10 years)."],
       ["MDCAT", "Medical &amp; Dental Colleges Admission Test by PM&amp;DC. 180 MCQs, no negative marking. MBBS needs 99, BDS 90."],
       ["ECAT", "Engineering College Admission Test by UET. 400 marks (100 MCQs × 4), negative marking. PEC minimum 132 (33%)."],
       ["SEET", "MUST's State Entry Examination Test for engineering and engineering technology."],
       ["LAT", "HEC Law Admission Test, needed for LLB."],
       ["PM&amp;DC", "Pakistan Medical &amp; Dental Council, the regulator for medical and dental admissions."],
       ["PEC", "Pakistan Engineering Council, which accredits engineering programs."],
       ["JAC", "Joint Admission Committee for MBBS/BDS in AJK public colleges (its website currently does not work)."],
       ["SZABMU", "Shaheed Zulfiqar Ali Bhutto Medical University, Islamabad; conducts MDCAT for AJK."],
       ["State Subject", "AJK residency certificate required for AJK-national seats."],
       ["Merit aggregate", "Weighted score for MBBS/BDS: 50% MDCAT + 40% HSSC + 10% SSC."],
       ["YAML", "A simple text format for structured data, used for the rule book."],
       ["BM25", "A keyword-based ranking method for searching documents."],
       ["RAG", "Retrieval-augmented generation: search documents, then answer from what was found."],
       ["MCP", "Model Context Protocol: a standard way to give AI assistants tools."],
       ["Pull request", "A proposed change on GitHub that a person reviews before it is merged."]], [35, 135])

# ---------------------------------------------------------------- build
doc = Doc(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
          title="JK Assistance - Manual, How It Works, Building an Agent, Interview Preparation", author="Faisal Ramzan",
          subject="Admission assistant for AJK students")
doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
print(f"wrote {OUT}")
