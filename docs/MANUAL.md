# JK Assistance - Manual (Admissions)

This manual covers:

1. Installing
2. Running on localhost
3. Using the portal
4. The REST API
5. MCP
6. Testing
7. How the assistant works
8. Implementation
9. Updating the data
10. Known gaps

---

## 1. Install

Requirements: Python 3.11+.

```bash
pip install -r requirements.txt
```

Optional: copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` so Claude writes the chat answers (model `claude-opus-5-5`, effort `medium`). Without a key, answers are rendered directly from the rule engine. Eligibility, marks, fees and dates are identical either way.

The two large prospectus PDFs are not in git; their extracted text is. To download the PDFs themselves:

```bash
python scripts/fetch_large_documents.py
```

## 2. Run on localhost

```bash
python -m uvicorn jk_assistance.api:app --port 8010 --reload
```

- Portal: http://localhost:8010
- API docs: http://localhost:8010/docs

To replay the data exactly as retrieved, fix "today":

```bash
JK_TODAY=2026-09-29 python -m uvicorn jk_assistance.api:app --port 8010
```

In PowerShell: `$env:JK_TODAY="2026-09-29"; python -m uvicorn jk_assistance.api:app --port 8010`

If you get `[Errno 10048] ... 8010`, another server (for example a preview) is already on that port. Stop it, or use `--port 8011`.

## 3. Using the portal

| Tab | What the student does |
|---|---|
| **1. Find my programs** | Pick the intermediate group. Enter HSSC and SSC marks as *obtained / out of* (e.g. 946 / 1100). Enter test scores if taken: **MDCAT obtained (max 180)**, **ECAT obtained (max 400)**, UAJK test, SEET and LAT as obtained / total. Optionally pick an interest, an institution, age, State Subject and Mathematics. The result shows a summary (how many programs are open, the next deadline), then one card per program with a **requirement / needed / you / pass-fail** table, chance, fees and seats, then the step-by-step application for each institution. |
| **2. How to apply** | Steps, document checklist (tickable), dates, age limit, reserved seats, scholarships, fee rules, contacts and sources, for UAJK, MUST and MBBS/BDS. MBBS/BDS shows the JAC-not-working warning with the working channels. |
| **Entry tests** | One card per test: total marks, minimum marks, format, fee, 2026 dates, merit formula, ECAT averages. |
| **Admission dates** | Upcoming dates first (days left, highlighted when 14 days or fewer), then recently passed ones, plus rules to remember. |
| **Ask a question** | Free text in English or Roman Urdu, with sources. Suggested questions are provided. |

**Navigation (right of the tabs):**
- **← Back** returns to the previous screen. The browser's own back button and **Alt+←** do the same, and results are kept.
- **⌂ Home** goes to "Find my programs".
- **✕ Clear** empties the current screen: marks and results on Find, the conversation in Chat, the ticks in How to apply.

After a check, the results offer **✎ Edit my marks**, **↺ Start over** and **Next: how to apply →**. Each screen also has its own address, e.g. `/#dates`, which can be bookmarked or shared.

Example questions:

- `I did FSc pre-medical 946/1100, matric 1010/1100, MDCAT 140/180 - I want MBBS or DPT`
- `FSc pre-engineering 880/1100, ECAT 210 - engineering`
- `ICS 64% computer science`
- `MDCAT passing marks` / `ECAT total marks`
- `How do I apply to UAJK?` / `how to apply for MBBS in AJK` / `mujhe MUST mein admission kaise milega`
- `UAJK last date`
- `I missed the deadline, can I still apply?` returns **ESCALATE**: contact the admission office.
- `How do I get my transcript?` returns **OFF_TOPIC**, because the assistant is admission-only.

## 4. REST API

| Method & path | Purpose |
|---|---|
| `GET /api/health` | status, today, program count, whether Claude is on |
| `POST /api/advise` | eligibility check (body below) |
| `GET /api/tests`, `GET /api/tests/{id}` | entry tests: `mdcat`, `ecat`, `uajk_entry_test`, `must_seet`, `hec_lat` |
| `GET /api/how-to-apply/{uajk\|must\|jac}` | steps, documents, contacts, dates |
| `GET /api/deadlines?institution=` | dated admission events + rules |
| `GET /api/programs?institution=&field=` | program catalog |
| `GET /api/institutions` | institutions, portals, contacts, website status |
| `GET /api/search?q=` | evidence search over the official sources |
| `POST /api/chat` | `{"message": "..."}`: the full assistant |

`POST /api/advise` body. Marks may be a percentage, or `{"obtained", "total"}`. For MDCAT and ECAT a plain number means marks obtained (out of 180 / 400).

```json
{"group": "pre_med",
 "hssc": {"obtained": 946, "total": 1100},
 "ssc": {"obtained": 1010, "total": 1100},
 "tests": {"mdcat": 140, "ecat": {"obtained": 210, "total": 400}, "uajk_entry_test": {"obtained": 62, "total": 100}},
 "interests": ["medicine", "health"], "institutions": ["jac", "uajk"],
 "age": 18, "state_subject": true, "studied_math": false}
```

Example:

```bash
curl -s -X POST http://localhost:8010/api/advise -H "Content-Type: application/json" -d "{\"group\":\"pre_eng\",\"hssc\":{\"obtained\":880,\"total\":1100},\"tests\":{\"ecat\":210},\"interests\":[\"engineering\"]}"
```

## 5. MCP

`mcp_server/server.py` (MCP Python SDK 2.x, `MCPServer`) exposes:

| Tool | Returns |
|---|---|
| `check_admission(group, hssc_obtained, hssc_total, ssc_obtained, ssc_total, mdcat_obtained, ecat_obtained, uajk_test_percent, seet_percent, lat_percent, interests, institutions, age, state_subject, studied_math)` | eligible programs with checklists, merit aggregate, chance, fees, how to apply |
| `get_test(test_id)` | max/min marks, format, fee, dates, formula |
| `how_to_apply(institution)` | steps, documents, contacts, dates (`uajk`, `must`, `jac`) |
| `admission_dates(institution)` | dated events + rules |
| `list_programs(institution, field)` | programs |
| `search_admission_sources(query)` | evidence snippets |
| `ask_jk_assistance(message)` | the full pipeline |

**Claude Code** (`.mcp.json`) / **Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{"mcpServers": {"jk-assistance": {"command": "python",
  "args": ["C:\\Users\\Faisal Ramzan\\Desktop\\AJK university VA\\mcp_server\\server.py"],
  "env": {"JK_DISABLE_LLM": "1"}}}}
```

For HTTP, run the command below; it serves `http://localhost:8765/mcp` (Streamable HTTP; the port can be set with `JK_MCP_PORT`). The MCP Inspector (`npx @modelcontextprotocol/inspector`) can connect to it.

```bash
python mcp_server/server.py --http
```

To smoke-test the server through the official client:

```bash
python scripts/mcp_smoke_test.py
```

## 6. Testing

```bash
python -m pytest -q
```

`tests/conftest.py` fixes today at 2026-09-29 and disables Claude.

`tests/test_advisor.py` covers:
- marks parsing;
- official MDCAT/ECAT max and min marks;
- the JAC not-working flag and its replacement channels;
- the MBBS checklist ("≥ 55% = 99 / 180" against "140 / 180 = 77.78%") and the merit aggregate;
- MDCAT 95: MBBS fails, BDS passes;
- a missing MDCAT gives "eligible after test";
- HSSC below 60%;
- ECAT accepted as "any one test", and ECAT below 132 with SEET still open;
- the Mathematics requirement and age limit;
- interest order, needs-info and open fields;
- chat intents, profile parsing, escalation and off-topic handling;
- YAML integrity and program references.

`tests/test_api.py` covers the endpoints end to end.

The notebook `notebooks/JK_Assistance_Samples.ipynb` holds executed samples: the test table, three sample students with checklists, merit aggregates for MDCAT 99-175, eight edge cases, how-to-apply guides, dates, 11 chat questions and an MCP call. Rebuild it with `python scripts/build_notebook.py`.

## 7. How the assistant works

```
student marks + group + interests
        |
        v
 advisor.normalize()   percentages from "946/1100", {obtained,total}, MDCAT/ECAT raw marks (max 180/400)
        |
        v
 advisor.assess()      per program: group - HSSC minimum - Mathematics - entry test(s) (any one) - age - State Subject - domicile
        |               -> checklist rows {criterion, required "≥ 55% = 99 / 180", yours "140 / 180 = 77.78%", pass/fail/pending/check}
        |               -> verdict: eligible | eligible_after_test | check_required | not_eligible
        |               -> PM&DC merit aggregate (MBBS/BDS), heuristic chance, fees, seats
        v
 how_to_apply()        steps + documents + contacts + dates for each institution with open programs
        |
        v
 chat: decision.route_message()  ESCALATE (exceptions, late applications, sensitive) | OFF_TOPIC (non-admission)
       assistant.answer()        intent: admission_advice | test_info | how_to_apply | deadlines | information
       evidence (BM25 over official pages/PDFs) -> Claude writes from the engine result + evidence, or deterministic markdown
```

Principles:

- **The rules decide.** Minimum marks, test thresholds, formulas, fees and dates come from `knowledge/*.yaml`, each with its source. Claude may only phrase them.
- **Show the arithmetic.** Every requirement is shown as needed vs yours, in marks out of the maximum.
- **Never block on a missing test.** If a test isn't taken yet, the program is "eligible if you pass the test" and shows the minimum needed.
- **Admission-only.** Anything else is redirected to the office contacts.
- **No dead links.** JAC is flagged as not working, and the working official channels are given.

## 8. Implementation

| File | Role |
|---|---|
| `jk_assistance/knowledge.py` | loads the YAML; `detect_institution` ("MUST" only as an acronym), `detect_test`; BM25 evidence index over YAML and admission sources |
| `jk_assistance/advisor.py` | `to_percent`, `normalize`, `assess` (checklist and verdict), `advise` (ranking by the student's interest order), `how_to_apply`, `upcoming_deadlines`, `test_info` |
| `jk_assistance/assistant.py` | chat router and profile parser (groups, "946/1100", "MDCAT 140", Roman Urdu), and markdown rendering |
| `jk_assistance/decision.py` | GUIDE / ASK_INFO / ALERT / ESCALATE / OFF_TOPIC |
| `jk_assistance/llm.py` | Anthropic SDK call (`claude-opus-5-5`, cached system prompt, server-side refusal fallback); returns `None` on any error so the deterministic answer is used |
| `jk_assistance/api.py` | FastAPI endpoints and the portal |
| `mcp_server/server.py` | MCP tools |
| `web/index.html` | the portal (vanilla JS + marked.js, light and dark) |

## 9. Updating the data

1. Fetch pages with `python scripts/fetch_pages.py <site> <url> ...`. Put PDFs in `documents/<site>/`, then run `python scripts/extract_docs.py <site>`. Scanned PDFs extract no text; read and transcribe them.
2. Edit `knowledge/admissions.yaml`: programs (groups, `min_percent`, `test_rules`, fees), tests (`max_marks`, `passing`) and application steps. Edit `knowledge/deadlines.yaml` for dates. Quote any value containing a comma.
3. When the next AJK MBBS round is announced, add its dates to `deadlines.yaml`. If the JAC site comes back, update `website_status` in `institutions.yaml`.
4. Run `python -m pytest -q`.

## 10. Known gaps

- There are no official closing merits, so "chance" is a heuristic.
- UAJK's BBA, LLB, B.Ed and BFA fee sheets are scans that haven't been transcribed (their files are in `documents/uajk/fee_structure/`). MUST's Pharm-D, DPT and management fees were not in the prospectus text.
- Maximum marks for MUST SEET, the UAJK entry test and LAT are not published, so the student enters them from their result card.
- AJKMC's website is unreachable.
