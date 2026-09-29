# JK Assistance

**A policy-aware AI student-services assistant for universities and medical colleges in Azad Jammu & Kashmir.**

JK Assistance helps two groups of students:

- **Students who have completed 12 years of education** (FSc / FA / ICS / I.Com / DAE / A-level). It tells them which programs they are eligible for at UAJK, MUST and the AJK medical colleges, gives a chance estimate, lists the entry tests (UAJK test, SEET, MDCAT, LAT), the documents, first-semester fees and admission deadlines, and explains how to apply.
- **Enrolled students and graduates**. It covers documentation and application processing (degree, transcript/DMC, verification, duplicate degree, migration, transfer, clearance, bonafide, English proficiency, re-checking, refunds). It also tracks fees, challans and deadlines, and semester promotion (promoted / probation / relegated / dropped, with what-if simulation).

It is built on the idea in the *Policy-Aware AI for Academic Progression* concept note. It is not just a chatbot: it combines

1. **a versioned policy knowledge layer**: official rules, fees with effective dates, forms and sources;
2. **rule engines**: promotion/probation, GPA/CGPA, dues and fine windows, deadlines, admission eligibility;
3. **event-driven monitoring**: a new grade, payment or deadline change re-evaluates the student;
4. **a decision layer**: every finding becomes **GUIDE**, **ASK_INFO**, **ALERT** or **ESCALATE** (to a human advisor queue);
5. **grounded answers**: Claude (`claude-opus-5-5`) phrases answers from numbered evidence only. Without an API key, the engines' results are rendered directly.

Institutions covered: **UAJK** (Muzaffarabad), **MUST** (Mirpur), **JAC AJ&K** (MBBS/BDS admissions), **Poonch Medical College** (Rawalakot), **MBBSMC** (Mirpur), **UHS Lahore** (MBBS/BDS degrees and transcripts). AJKMC is listed, but its website was unreachable.

## Quick start (localhost)

```bash
pip install -r requirements.txt
```

```bash
python scripts/seed_demo.py
```

```bash
python -m uvicorn jk_assistance.api:app --port 8010
```

Open http://localhost:8010. Tabs: **Ask** (chat), **Admission advisor**, **Deadlines**, **My dashboard**, **Documents & services**, **Applications**, **Advisor queue**.

Optional: set `ANTHROPIC_API_KEY` (see `.env.example`) so Claude writes the answers. Everything else works without it.

## Use it from Claude (MCP)

```bash
python mcp_server/server.py
```

Add it to Claude Desktop / Claude Code as a stdio MCP server. There are 9 tools: `advise_admission`, `get_service`, `get_deadlines`, `evaluate_progression`, `student_dashboard`, `start_application`, `search_knowledge`, `list_services`, `ask_jk_assistance`. See [mcp_server/README.md](mcp_server/README.md).

## Test

```bash
python -m pytest -q
```

The 46 tests cover the MUST grading table and worked examples, every promotion path (probation, summer waiver, drop, relegation, second-half reset), versioned fee selection, advisor eligibility, the decision routing, YAML integrity and the full API flow. They run on an isolated copy of the demo data.

## Sample notebook

[notebooks/JK_Assistance_Samples.ipynb](notebooks/JK_Assistance_Samples.ipynb) has 38 executed cells of sample tests with saved outputs. It covers procedures and versioned fees, four admission-advisor profiles, seven promotion cases, what-if scenarios, dashboards, events, application tracking, 13 chat questions, evidence search, the escalation queue and the MCP server. Open it in VS Code or Jupyter, or rebuild and re-run it:

```bash
python scripts/build_notebook.py
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/MANUAL.md](docs/MANUAL.md) | Full manual: install, localhost, portal walkthrough, REST API, MCP setup, testing, how the agent works, implementation details, updating the knowledge |
| [knowledge/README.md](knowledge/README.md) | Data sources, trust levels, fee versioning, known gaps, and how to update |
| [mcp_server/README.md](mcp_server/README.md) | MCP tools and client configuration |

## Repository layout

```
jk_assistance/        the application (knowledge, engines, decision layer, API, Claude composer)
mcp_server/server.py  MCP server exposing the tools
web/index.html        the student portal (served by the API)
knowledge/*.yaml      curated, versioned rules: institutions, services, admissions, deadlines, progression
documents/            official forms, fee sheets and prospectuses (PDF/DOCX) + extracted text
raw/                  fetched web pages (HTML + clean text) with their source URL
scripts/              data collection (fetch_pages, extract_docs), demo seeding, large-file download
tests/                pytest suite
data/                 runtime JSON store (students, applications, events, escalations) - not committed
```

## Important limitations

- The information was retrieved on **2026-09-29**. Fees and dates change; every answer shows its source and date.
- UAJK has **not published** its semester promotion rules online, so JK Assistance does not guess and escalates such questions instead. MBBS promotion (UHS) is not modelled either.
- The JAC admission portal is behind a Cloudflare check. JAC facts (merit formula, processing fee, 2026 dates) come from a third-party site and are marked **"verify"**.
- The **chance estimate is a heuristic** (margin above the minimum, and program demand). No verified closing-merit data exists online.
- All demo students are fictional.
