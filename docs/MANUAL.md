# JK Assistance - Manual

This manual covers:

1. Installing
2. Running on localhost
3. Using the portal
4. The REST API
5. Using JK Assistance through MCP
6. Testing
7. How the agent works
8. Implementation by module
9. Updating the knowledge
10. Deploying
11. Known gaps

---

## 1. Install

Requirements: Python 3.11+ (developed on 3.12, Windows 11).

```bash
pip install -r requirements.txt
```

The two very large prospectus PDFs (37 MB and 43 MB) are not in git. Their extracted text is committed, so the assistant works without them. To download the PDFs themselves:

```bash
python scripts/fetch_large_documents.py
```

### Optional: Claude for answer wording

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`, or set it in your shell. The model is `claude-opus-5-5` at effort `medium`; override with `JK_MODEL` / `JK_EFFORT`. Without a key, or with `JK_DISABLE_LLM=1`, the assistant renders the rule-engine results and the evidence itself.

---

## 2. Run on localhost

```bash
python scripts/seed_demo.py
```

```bash
python -m uvicorn jk_assistance.api:app --port 8010 --reload
```

- Portal: http://localhost:8010
- Interactive API docs (Swagger): http://localhost:8010/docs
- Health: http://localhost:8010/api/health

To replay the demo exactly as it was built, fix "today":

```bash
JK_TODAY=2026-09-29 python -m uvicorn jk_assistance.api:app --port 8010
```

(PowerShell: `$env:JK_TODAY="2026-09-29"; python -m uvicorn jk_assistance.api:app --port 8010`)

`seed_demo.py` resets `data/`. It creates six fictional records:

| ID | Who | What it demonstrates |
|---|---|---|
| S-001 | MUST BS CS, semester 3 | first probation, pending results with a relegation prediction, attendance below 75%, overdue hostel dues, dues before pre-registration, re-checking window |
| S-002 | MUST BS Maths, semester 8 | probation waived by the summer semester; degree requirements met, so clearance and then the degree |
| S-003 | UAJK BS English | semester fee inside the 10% fine window (weeks 4-6); UAJK promotion rules unpublished, so no guessing |
| S-004 | MBBS graduate, PMC | degree and transcript through the UHS portal |
| A-001 | Applicant, FSc pre-medical 82%, MDCAT 71% | MBBS/DPT/allied health options, merit aggregate |
| A-002 | Applicant, ICS 64% | computing/engineering eligibility at UAJK and MUST |

---

## 3. Using the portal

| Tab | Use it for |
|---|---|
| **Ask** | Free-text questions in English or Roman Urdu. Pick a student in "Ask as" for personal questions ("Am I on probation?"). Every answer shows the action pill (GUIDE / ASK_INFO / ALERT / ESCALATE) and an **Evidence** list of sources. |
| **Admission advisor** | For students after 12 years of education: enter group, HSSC %, optional SSC/MDCAT %, age, interests and institution. You get the eligible programs, a heuristic chance, tests, first-semester fees, how to apply, the document checklist and upcoming deadlines. |
| **Deadlines** | All dated deadlines (admission last dates, merit lists, scholarship dates) with days left, plus standing rules (UAJK fee fine window, re-checking windows, MUST registration, refund, withdrawal, migration submission). |
| **My dashboard** | Proactive findings for a student, semester-by-semester progress, CGPA, dues with "Mark paid" (an event that re-runs the monitor), and a **what-if** simulator for pending courses. |
| **Documents & services** | The full checklist for any procedure: fees in force today (with previous versions), documents, steps, deadlines, processing time, forms (local copy + official link), sources. |
| **Applications** | Open a tracked case for a service, tick documents, record fee payment and submission. Deadlines such as "submit migration within 15 days of paying" then appear on the dashboard. |
| **Advisor queue** | Cases escalated to a human (exceptions, appeals, sensitive situations, unpublished rules, exhausted probation/relegation). Resolve them here. |

Example questions:

- `How do I get my degree from MUST?`
- `UAJK migration certificate documents and fee`
- `MBBS transcript from UHS`
- `I did FSc pre-medical with 82%, matric 88%, MDCAT 71%, I want MBBS or DPT`
- `ICS 64% which programs can I apply for in computing?`
- `UAJK admission last date`
- `mujhe MUST se clearance certificate kaise milega`
- (as S-001) `Am I on probation? What happens if I fail again?`
- `Can I get an extension for my fee deadline?` (this one is escalated to a human)

---

## 4. REST API

All endpoints return JSON. Full schema at `/docs`.

| Method & path | Purpose |
|---|---|
| `GET /api/health` | status, today, whether Claude is on, index size |
| `GET /api/institutions` | institution directory with contacts and portals |
| `GET /api/services?institution=uajk` | list procedures |
| `GET /api/services/{id}` | full checklist with the fee version in force today |
| `GET /api/programs?institution=must` | admission program catalog |
| `POST /api/advise` | admission advice for a 12th-grade profile |
| `GET /api/deadlines?institution=&audience=applicants` | dated deadlines + relative rules |
| `GET /api/search?q=...` | BM25 evidence search |
| `GET /api/students`, `GET /api/students/{id}` | student records |
| `GET /api/students/{id}/dashboard` | triaged findings, progression, dues, applications |
| `POST /api/students/{id}/events` | `grade_posted`, `attendance_updated`, `payment`, `due_added`, `result_declared`; returns fresh findings |
| `POST /api/students/{id}/what-if` | re-evaluate promotion with hypothetical marks |
| `POST /api/applications`, `PATCH /api/applications/{id}`, `GET /api/applications` | application tracking |
| `GET /api/escalations`, `POST /api/escalations/{id}/resolve` | human-advisor queue |
| `POST /api/chat` | the full assistant pipeline |

Examples:

```bash
curl -s -X POST http://localhost:8010/api/chat -H "Content-Type: application/json" -d "{\"message\":\"UAJK bonafide certificate\"}"
```

```bash
curl -s -X POST http://localhost:8010/api/advise -H "Content-Type: application/json" -d "{\"group\":\"pre_eng\",\"hssc_percent\":71,\"interests\":[\"engineering\"]}"
```

```bash
curl -s -X POST http://localhost:8010/api/students/S-001/events -H "Content-Type: application/json" -d "{\"type\":\"grade_posted\",\"payload\":{\"semester\":3,\"code\":\"CS-301\",\"percent\":61}}"
```

```bash
curl -s -X POST http://localhost:8010/api/students/S-001/what-if -H "Content-Type: application/json" -d "{\"results\":{\"CS-301\":55,\"CS-303\":40}}"
```

---

## 5. Using JK Assistance through MCP

`mcp_server/server.py` exposes the same engines as MCP tools (MCP Python SDK 2.x, `MCPServer`).

**Claude Code**: add a `.mcp.json` in any project (or run `claude mcp add`):

```json
{
  "mcpServers": {
    "jk-assistance": {
      "command": "python",
      "args": ["C:\\Users\\Faisal Ramzan\\Desktop\\AJK university VA\\mcp_server\\server.py"],
      "env": {"JK_DISABLE_LLM": "1"}
    }
  }
}
```

**Claude Desktop**: put the same `mcpServers` block in `%APPDATA%\Claude\claude_desktop_config.json` and restart Claude Desktop.

`JK_DISABLE_LLM=1` is recommended under MCP: the tools return engine results and evidence, and the calling Claude writes the answer. That avoids a second model call.

**HTTP transport** (remote clients, MCP Inspector):

```bash
python mcp_server/server.py --http
```

This listens on `http://localhost:8765/mcp` (change the port with `JK_MCP_PORT`). To inspect it interactively:

```bash
npx @modelcontextprotocol/inspector
```

Then connect to `http://localhost:8765/mcp` (transport: Streamable HTTP).

| Tool | Returns |
|---|---|
| `advise_admission(group, hssc_percent, ssc_percent, mdcat_percent, interests, institutions, age, state_subject, studied_math)` | eligible programs, chance, tests, fees, how to apply, deadlines |
| `list_services(institution)` / `get_service(service_id)` | procedure list / full checklist with the fee in force today |
| `get_deadlines(institution, audience, include_past_days)` | dated deadlines + relative rules |
| `evaluate_progression(semesters, program_type, institution)` | promotion outcome per semester, probation state, GPA/CGPA |
| `student_dashboard(student_id)` | triaged proactive findings |
| `start_application(service_id, student_id)` | a tracked application case |
| `search_knowledge(query, institution, k)` | evidence snippets with source and trust |
| `ask_jk_assistance(message, student_id)` | the complete pipeline |

Then ask Claude, for example: *"Using jk-assistance, what documents do I need for a UAJK duplicate degree and how much is the fee?"*

---

## 6. Testing

```bash
python -m pytest -q
```

- `tests/conftest.py` fixes today at 2026-09-29, disables Claude, and seeds an **isolated temporary data directory**, so tests never touch `data/`.
- `tests/test_engines.py` covers:
  - MUST's GP table, and both published worked examples (63.92% gives 2.65, 59.0% gives 2.45);
  - the flag for the 2.65-vs-2.70 conflict between two MUST pages;
  - F grades excluded from the percentage; lab and attendance failures;
  - every promotion path;
  - fee versioning (7,500 before 28 July 2026, 9,080 from that date);
  - forms exist on disk; YAML integrity;
  - advisor eligibility, the merit aggregate and missing-info handling;
  - decision routing and sensitive-message escalation.
- `tests/test_api.py` covers the end-to-end API: chat intents, ASK_INFO for an ambiguous institution, ESCALATE for exception requests, the dashboard (probation, attendance, overdue, UAJK fine window), events clearing alerts, the application lifecycle with the 15-day migration deadline, and deadlines/search.

**Manual test checklist (localhost):** run each example question in section 3 and check the action pill and the sources. On the dashboard, click "Mark paid" for S-001's hostel dues: the overdue alert disappears. Open the S-001 what-if and set CS-301=55, CS-303=40: the outcome is relegated to semester 3.

**Sample notebook**: `notebooks/JK_Assistance_Samples.ipynb` runs sample inputs through every component on an isolated copy of the demo data, with today fixed at 2026-09-29. Open it in VS Code or Jupyter and choose "Run All". To regenerate it with fresh outputs:

```bash
python scripts/build_notebook.py
```

If `ANTHROPIC_API_KEY` is set when Jupyter starts, its last cell also shows a Claude-written answer.

**MCP smoke test**: this spawns the server and calls tools through the official client:

```bash
python scripts/mcp_smoke_test.py
```

---

## 7. How the agent works

```
 student / applicant / MCP client
            |
            v
  +-------------------+     sensitive, exception or appeal? --> ESCALATE (human queue)
  |  Router           |---- student status?  --> Monitor (progression, dues, attendance, deadlines, applications)
  |  (assistant.py)   |---- admission?       --> Advisor (eligibility, tests, fees, chance, how to apply)
  +-------------------+---- deadlines?       --> Deadline calendar + relative rules
            |           \-- procedure?       --> Service catalog (documents, fee version for today, steps, forms)
            v
  Decision layer (decision.py): GUIDE | ASK_INFO | ALERT | ESCALATE
            |
            v
  Evidence retrieval (BM25 over curated YAML + every fetched page and document, with source and trust)
            |
            v
  Composer: Claude (claude-opus-5-5) writes ONLY from the engine result + numbered evidence
            or, with no key, deterministic markdown rendering
```

Principles (from the concept note):

1. **Rules decide, the LLM only phrases.** Eligibility, fees, deadlines and promotion outcomes are computed deterministically from `knowledge/*.yaml`. Claude is told it may not contradict the structured result or invent numbers.
2. **Versioned policy.** Each fee has versions with `effective_from`, and the engine picks the one in force on the question date. Example: MUST degree fees changed on 28 July 2026. Rule sets carry an effective cohort, e.g. `must.semester.v2017` from Spring 2017.
3. **Event-driven and proactive.** `POST /events` (grade, attendance, payment, new due, result declared) re-runs `monitor.scan()`. Findings include predicted future consequences: for pending results, the engine simulates failing versus passing the pending courses.
4. **Know when to stop.** Missing data gives ASK_INFO. Unpublished rules (UAJK promotion), exhausted probation or relegation, dropped status, exceptions, appeals, extensions and sensitive situations give ESCALATE, and a ticket goes to the human advisor queue.
5. **Transparent provenance.** Every service, program, deadline and rule stores its source URL and `trust` (official/secondary). Answers show the evidence, and secondary facts are labelled "verify".

---

## 8. Implementation by module

| Module | Responsibility |
|---|---|
| `jk_assistance/config.py` | paths, model and effort, `today()` (overridable with `JK_TODAY`), alert window, LLM switch |
| `jk_assistance/knowledge.py` | loads the YAML layer; `fee_version()` picks the fee in force on a date; `detect_institution()`; `match_services()` (deterministic keyword routing); builds the evidence corpus (~1,560 chunks from YAML, `raw/**/*.txt`, `documents/**/text/*.txt`) and a BM25 index boosted toward curated entries and down-weighted for secondary sources |
| `jk_assistance/progression.py` | MUST grading (GP table, letter grades, fraction rule, F excluded, lab and attendance) and promotion replay across semesters (probation, summer waiver, drop, relegation targets, first probation not carried into the second half, one relegation and two probations max). Also `what_if()`, degree check (CGPA 2.5 / 57.5%), attendance, maximum duration. Returns `rules_unavailable` for UAJK and UHS. |
| `jk_assistance/advisor.py` | 12th-grade advisor: group, minimum %, Mathematics requirement, age limits (UAJK 23, MUST 24), MDCAT thresholds, State Subject, merit aggregate (10/40/50), heuristic chance bands, tests, fees, application process, upcoming deadlines |
| `jk_assistance/monitor.py` | findings for students (progression, projection, degree readiness, CGPA, policy conflicts, attendance, dues including UAJK fine windows, MUST pre-registration, re-checking windows, duration, application documents and deadlines) and for applicants (admission deadlines, missing profile) |
| `jk_assistance/decision.py` | `decide()` maps each finding to an action; `route_message()` catches sensitive and exception requests; `triage()` sorts and records escalations |
| `jk_assistance/applications.py` | application cases: checklist from `required_documents`, fees fixed on the application date, status machine (draft, documents_ready, fee_paid, submitted, in_process, completed/rejected), relative deadlines |
| `jk_assistance/assistant.py` | the orchestrator: intent routing, profile parsing from text ("FSc pre-medical 82%, MDCAT 71"), evidence gathering, Claude or deterministic rendering |
| `jk_assistance/llm.py` | Anthropic SDK call: `claude-opus-5-5`, effort medium, cached system prompt, server-side refusal fallback (`fallbacks="default"`), typed error handling; returns `None` on failure so the deterministic answer is used |
| `jk_assistance/store.py` | JSON-file persistence (`data/*.json`); swap for a database in production |
| `jk_assistance/api.py` | FastAPI app, the REST endpoints above, serves `web/index.html` and `/documents/*` |
| `mcp_server/server.py` | MCP tools over the same functions (stdio or streamable HTTP) |
| `web/index.html` | the dependency-free portal (vanilla JS + marked.js), light and dark themes |
| `scripts/fetch_pages.py`, `scripts/extract_docs.py` | the data collection pipeline used to build `raw/` and `documents/` |

**Student record format** (see `scripts/seed_demo.py`):

```json
{"id": "S-001", "type": "student", "institution": "must", "program_type": "bs4", "duration_key": "bs_bba_bsc",
 "result_declared_on": "2026-09-22", "next_semester_start": "2026-10-05", "semester_start": "2026-08-31",
 "semesters": [{"number": 1, "courses": [{"code": "CS-101", "credits": 4, "percent": 71, "attendance": 90, "lab_percent": null}],
                "summer": []}],
 "dues": [{"id": "D1", "kind": "semester_fee", "semester": 4, "title": "...", "amount": 42235, "due_date": "2026-10-03", "paid": false}]}
```

Applicants use `"type": "applicant"` with `group`, `hssc_percent`, `ssc_percent`, `mdcat_percent`, `interests`, `target_institutions`, `age`, `state_subject`.

---

## 9. Updating the knowledge

See [knowledge/README.md](../knowledge/README.md). In short:

1. Re-fetch pages with `python scripts/fetch_pages.py <site> <url> ...`.
2. Download new forms into `documents/<site>/` and run `python scripts/extract_docs.py <site>`. Scanned PDFs extract no text; read them and transcribe the facts into the YAML.
3. Edit `knowledge/*.yaml`. For a changed fee, **add a new version** with its `effective_from`; don't overwrite the old one.
4. Quote any YAML value that contains a comma (`"..."`). `test_yaml_values_not_split_by_commas` catches mistakes.
5. Run `python -m pytest -q`.

---

## 10. Deploying

- Run behind a reverse proxy with `uvicorn jk_assistance.api:app --host 0.0.0.0 --port 8010 --workers 2`.
- Replace `store.py` with a database, and add authentication before real student records are stored (the demo has none).
- Schedule a daily sweep that calls `/api/students/{id}/dashboard` for each student and sends ALERT/ESCALATE findings by SMS or email.
- Keep `ANTHROPIC_API_KEY` in the server's secret store, never in the repository.

---

## 11. Known gaps

- AJKMC's website was unreachable; there is no AJKMC-specific data.
- JAC pages are behind a Cloudflare challenge; their facts come from a secondary source and are labelled.
- UAJK BS promotion rules and UHS MBBS promotion rules are not published or ingested, so those questions are escalated.
- Some fee sheets are scanned and not transcribed: UAJK BBA, LLB, B.Com, B.Ed, BFA, MPhil and PhD sheets (the files are in `documents/uajk/fee_structure/`), and MUST Pharm-D/DPT and management fees.
- MUST's per-program fees are from the 2024-25 prospectus; UAJK's are for the 2025-29 sessions (UAJK notes about 10% annual increases).
- The chance estimate is a heuristic, not a merit prediction.
