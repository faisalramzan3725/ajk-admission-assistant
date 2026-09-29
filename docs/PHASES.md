# JK Assistance - complete documentation, phase by phase

JK Assistance helps students in Azad Jammu & Kashmir who have finished 12 years of education decide **where to apply**, check **whether they are eligible** (including MDCAT out of 180 and ECAT out of 400), and follow **the exact steps and dates to enrol**.

The system is built in 10 phases. Each phase below lists its purpose, inputs, outputs, how it works, how to run it, how to check it, and its limits.

| # | Phase | Main files |
|---|---|---|
| 0 | Goal and design | `README.md`, this file |
| 1 | Source discovery and collection | `scripts/fetch_pages.py`, `jk_assistance/sources.py`, `raw/`, `documents/` |
| 2 | Extraction (text, scans) | `scripts/extract_docs.py`, `documents/*/text/` |
| 3 | Knowledge curation | `knowledge/institutions.yaml`, `admissions.yaml`, `deadlines.yaml` |
| 4 | Evidence index (retrieval) | `jk_assistance/knowledge.py` |
| 5 | Eligibility engine | `jk_assistance/advisor.py` |
| 6 | Conversation layer | `jk_assistance/assistant.py`, `decision.py`, `llm.py` |
| 7 | Interfaces: portal, API, MCP | `web/index.html`, `jk_assistance/api.py`, `mcp_server/server.py` |
| 8 | Testing and verification | `tests/`, `notebooks/`, `scripts/mcp_smoke_test.py` |
| 9 | Automatic updating (update agent) | `scripts/update_agent.py`, `knowledge/sources.yaml`, `.github/workflows/update-sources.yml` |
| 10 | Operations (the yearly admission cycle) | this file, section 10 |

---

## Phase 0 - Goal and design

**Problem.** Students leaving intermediate college often don't know:
- which programs their group (pre-medical, pre-engineering, ICS, FA, I.Com, DAE, A-level) and marks allow;
- what MDCAT or ECAT score is needed;
- which documents to prepare;
- where and when to apply.

The official information is spread over many websites and scanned PDFs, and one key site (JAC) is down.

**Design principles** (from the policy-aware AI idea in the original concept note):
1. **Rules decide, AI only phrases.** Eligibility, marks, fees and dates are computed deterministically from curated, sourced data. The LLM (Claude) may only word the answer.
2. **Show the arithmetic.** Every requirement is displayed as *needed* vs *yours*, e.g. `≥ 55% = 99 / 180` vs `140 / 180 = 77.78%`.
3. **Traceability.** Every fact carries a source URL and a trust level (official or secondary).
4. **Know when to stop.** Missing data gives ASK_INFO. Exceptions, late applications and sensitive cases give ESCALATE (contact the office). Non-admission topics give OFF_TOPIC.
5. **No dead ends.** Broken official sites (JAC) are flagged and replaced by working official channels.
6. **Keep fresh automatically, verify by a human.** An agent watches the sources daily and a person approves changes.

---

## Phase 1 - Source discovery and collection

**Purpose:** get the official admission information onto disk, with its origin recorded.

**Inputs:** official websites.

| Body | Sources |
|---|---|
| UAJK | admission procedure, eligibility, required documents, reserved seats, programs, fee structure, scholarships, contacts |
| MUST | admissions, Fall 2026 eligibility criteria (PDF), merit-list schedule, semester rules (admission and age sections), prospectus 2024-25 |
| PM&DC | MDCAT-2026 notices, reschedule press release, 8 Apr 2026 notification, Admissions Regulations 2025 |
| SZABMU | MBBS admission page |
| UET | ECAT statistics (aggregates only) |
| Poonch Medical College, MBBSMC | admission pages |
| Secondary | gotest.com.pk (last JAC cycle only) |

**Outputs:**
- `raw/<site>/<slug>.html` + `.txt`: pages. Each `.txt` starts with `SOURCE: <url>`.
- `documents/<site>/*.pdf|jpg`: official documents.

**How it works:** `jk_assistance/sources.py` fetches with a browser-like User-Agent and cleans the HTML (removes menus, scripts and footers, then keeps the main content). It also lists document links (PDF, JPG, DOCX). JavaScript-only pages (MBBSMC) were captured in a real browser and saved as text. Cloudflare-blocked sites (JAC) are **not** bypassed; they are marked as down.

**Run:**

```bash
python scripts/fetch_pages.py uajk https://uajk.edu.pk/admission-procedure/
```

**Check:** each `.txt` has a `SOURCE:` line, and the printed `DOC:` lines show new PDFs.

**Limits and decisions:**
- `pmc.edu.pk` is a Faisalabad institution; Poonch Medical College is `pmcrajk.edu.pk`.
- The UET statistics file lists candidate names, so only the aggregate figures were kept and the file was deleted.

## Phase 2 - Extraction (text from PDFs and scans)

**Purpose:** make documents searchable and readable.

**Inputs:** `documents/<site>/*.pdf|docx`.

**Outputs:** `documents/<site>/text/<name>.txt`.

**How it works:** `pypdf` reads PDF text and `python-docx` reads Word files. A near-zero character count means a **scanned** document. Scans (UAJK fee sheets, the MUST merit-list notice, the MUST degree form) were read visually, and the facts were transcribed into the YAML in Phase 3 with the scan kept as the source.

**Run:**

```bash
python scripts/extract_docs.py pmdc
```

It prints character counts per file.

**Limits:** these scanned UAJK fee sheets are not transcribed yet: BBA, LLB, B.Com, B.Ed, BFA, MPhil and PhD.

## Phase 3 - Knowledge curation (the policy layer)

**Purpose:** turn sources into precise, machine-usable, sourced facts.

**Outputs:**

| File | Contents |
|---|---|
| `institutions.yaml` | UAJK, MUST, JAC (with `website_status: NOT WORKING` and `working_channels`), PMC, MBBSMC, AJKMC, SZABMU, PM&DC, UET: portals and contacts |
| `admissions.yaml` → `tests` | For each test: `max_marks`, `passing` (percent and marks), format, fee, dates, merit formula, averages, sources and trust. MDCAT: 180, MBBS 99, BDS 90, 50/40/10. ECAT: 400, PEC 132. SEET: 33%. UAJK test: 50%. LAT: 50%. |
| `admissions.yaml` → `application_process` | For uajk, must and jac: ordered steps, document checklist, age limit, reserved seats, scholarships, fee and refund rules |
| `admissions.yaml` → `programs` | 40 programs, each with `groups`, `min_percent`, `test_rules` (the student needs **any one**), `math_required`, `state_subject_required`, `fees` (session), `seats`, `demand` |
| `deadlines.yaml` | Dated events, each with a `link` (where the student acts), `source` and `trust`, plus admission rules |
| `sources.yaml` | The watch list for the update agent (Phase 9) |

**Rules for editing:**
- Every fact needs a source.
- Mark third-party facts `trust: secondary`.
- Quote YAML values that contain commas (a test enforces this).
- Never link students to a dead site.

**Check:**

```bash
python -m pytest -q tests/test_advisor.py -k "yaml or references or mdcat_and_ecat"
```

## Phase 4 - Evidence index (retrieval)

**Purpose:** find the official text behind any answer.

**How it works:** `knowledge.py` builds about 1,450 chunks:
- every institution, test, application process, program and date from the YAML;
- every `raw/**/*.txt` and `documents/**/text/*.txt`, split into ~1,400-character pieces with overlap.

A **BM25** keyword index ranks them. Curated YAML chunks are boosted 1.3×, and secondary sources are down-weighted to 0.8×. Institution filtering uses `detect_institution`, which only matches "MUST" as the uppercase acronym, because "must" is also an English word.

**Run:**

```bash
curl "http://localhost:8010/api/search?q=MDCAT%20passing%20marks"
```

**Limits:** it matches keywords, not meaning. That is sufficient because answers are driven by the structured engine, with retrieval only supplying evidence.

## Phase 5 - Eligibility engine (the core)

**Purpose:** decide, per program, whether the student can apply, and show exactly why.

**Input profile:**
- `group`;
- `hssc` and `ssc` (percent, `"946/1100"` or `{obtained, total}`);
- `tests` (MDCAT and ECAT as marks out of 180 / 400; others as percent or obtained/total);
- `interests`, `institutions`, `age`, `state_subject`, `studied_math`.

**Steps:**
1. **Normalise:** convert every mark to a percentage. For MDCAT/ECAT a plain number is raw marks, so MDCAT 95 means 95/180.
2. **Assess each program:**

   | Criterion | Rule |
   |---|---|
   | Group | must be in the program's accepted groups |
   | HSSC | ≥ `min_percent` (or "check" if not published) |
   | Mathematics | when the program needs it and the group is pre-medical, FA or I.Com |
   | Tests | pass if **any one** accepted test passes, pending if none taken yet, fail if all taken ones fail |
   | Age | UAJK ≤ 23, MUST ≤ 24 |
   | AJK State Subject | required for AJK public MBBS/BDS seats |
   | Domicile proof | for SZABMU quota seats |

   Each row is `{criterion, required, yours, status: pass | fail | pending | check}`.
3. **Verdict:**
   - `not_eligible` if anything fails;
   - `eligible_after_test` if only a test is pending;
   - `check_required` if unpublished items remain;
   - otherwise `eligible`.
4. **Merit aggregate** for MBBS/BDS (PM&DC): `0.5·MDCAT% + 0.4·HSSC% + 0.1·SSC%`.
5. **Chance** (heuristic, labelled as such):
   - medical: the aggregate, noting that closing merits are unpublished;
   - ECAT programs: comparison with UET's Fall 2026 group average;
   - otherwise: margin bands adjusted for program demand.
6. **Ranking:** open programs first, then the student's own order of interests, then readiness, then margin.
7. **How to apply** for each institution with open programs: steps, documents, contacts and dates (each date with a link).

**Run:** `POST /api/advise`, or the "Find my programs" tab.

**Check:** `tests/test_advisor.py` covers every rule and edge case. The notebook, section 4, shows eight edge cases.

**Limits:** "chance" is not a merit prediction, because no official closing merits are published.

## Phase 6 - Conversation layer

**Purpose:** answer free-text questions (English or Roman Urdu) safely.

**How it works (`assistant.answer`):**
1. `decision.route_message`:
   - sensitive topics, exceptions, late applications and appeals give **ESCALATE** (office contacts);
   - non-admission topics give **OFF_TOPIC**.
2. `parse_profile` pulls the group, `946/1100` style marks, `MDCAT 140`, `ECAT 210`, age, State Subject and interests out of the text. It masks "pre-medical" and "pre-engineering" so the group isn't mistaken for an interest.
3. Intent routing:

   | Question | Intent |
   |---|---|
   | marks or group given | admission advice |
   | a test named, no profile | test info |
   | a date question | deadlines |
   | an apply/steps/documents question | how to apply (MBBS maps to the medical process) |
   | anything else | information |
4. Evidence: the top 6 BM25 chunks.
5. Composer: if an API key is set, `llm.py` calls **Claude `claude-opus-5-5`**. It gets a cached system prompt and may use only the engine result and numbered evidence; a refusal falls back to another model server-side. Any error gives the deterministic markdown answer, which always works.

**Check:** `tests/test_advisor.py::test_chat_intents`, plus the notebook's section 7 (11 questions).

## Phase 7 - Interfaces

**Web portal (`web/index.html`),** in the order of a student's journey:
1. **Find my programs:** labelled inputs (MDCAT max 180, ECAT max 400), a summary (programs open, next deadline as a link), and program cards with the needed-vs-yours table.
2. **How to apply:** steps, a tickable document checklist, dates, contacts, and the JAC warning with working channels.
3. **Entry tests:** max/min marks, format, fee, dates.
4. **Admission dates:** upcoming first. Each has a clickable title, a "Go →" button (portal, merit lists) and a link to the official notice.
5. **Ask a question:** chat with sources.

**REST API (`api.py`):** `/api/advise`, `/api/tests`, `/api/how-to-apply/{uajk|must|jac}`, `/api/deadlines`, `/api/programs`, `/api/institutions`, `/api/search`, `/api/chat`, `/api/health`. Interactive docs are at `/docs`.

**MCP server (`mcp_server/server.py`):** `check_admission`, `get_test`, `how_to_apply`, `admission_dates`, `list_programs`, `search_admission_sources`, `ask_jk_assistance`. It works over stdio (Claude Desktop, Claude Code) or `--http`. See `mcp_server/README.md`.

## Phase 8 - Testing and verification

| Layer | How |
|---|---|
| Unit and integration | `python -m pytest -q`: 49 tests (engine, API, update agent) |
| Samples | `notebooks/JK_Assistance_Samples.ipynb`: executed outputs. Rebuild with `python scripts/build_notebook.py`. |
| MCP | `python scripts/mcp_smoke_test.py`: real client calls |
| Browser | each tab checked in a browser, including the clickable dates |
| Continuous | `.github/workflows/tests.yml` runs the tests on every push and PR |

## Phase 9 - Automatic updating (the update agent)

**Purpose:** notice when official admission information changes, without anyone checking 20 websites by hand.

**Inputs:**
- `knowledge/sources.yaml`: 23 sources, each with what to watch (`dates`, `fees`, `rules`, `links`, `status`);
- `knowledge/source_state.json`: the previous run.

**One run (`scripts/update_agent.py`):**
1. **FETCH** every source, recording reachability. Sites known to be down (JAC, AJKMC, mdcat.pmdc.pk) are checked too, so you learn when they return.
2. **DIFF** the page text against the previous version, and save the fresh text to `raw/`.
3. **DETECT** in the *added* lines:
   - dates (including UAJK's stylised digits);
   - rupee amounts;
   - percentage and minimum-marks sentences;
   - admission keywords;
   - newly linked PDFs or notices.
4. **LINKS:** health-check every link students are shown.
5. **CALENDAR:** flag institutions with no upcoming date, meaning the next cycle needs adding.
6. **PROPOSE (optional):** Claude reads the changed lines and returns draft `deadlines.yaml` entries as validated JSON, each with an evidence quote and confidence.
7. **REPORT:** `reports/update_report.md` and `reports/proposals.json`, and the flag `changed=true|false`.

**Automation:** `.github/workflows/update-sources.yml` runs daily at 08:00 PKT (or on demand). When `changed=true` it pushes a branch and opens a **pull request** whose description is the report. A person applies the verified changes to the YAML and merges; then the tests run.

**Why not fully automatic edits:** fees, dates and minimum marks are official facts. The agent finds them; a human confirms them.

**Check:**

```bash
python scripts/update_agent.py --no-llm
```

- **Live run (2026-09-29):** 20 of 23 sources were reachable, with the 3 known-down sites reported.
- **Simulated page edit:** the agent correctly reported "05 October 2026" and the "last date extended" line.
- **Tests:** `tests/test_update_agent.py`.

**Limits:**
- Pages that render only with JavaScript (MBBSMC) or sit behind Cloudflare (JAC) can't be read by the agent; it only reports their status.
- Scanned notices are detected as new links but must be read by a person.
- GitHub Actions gives private repos 2,000 free minutes a month; one agent run takes about 3-5 minutes, so the daily schedule uses about 150.

**One-time setup** (in the GitHub repo):
1. **Settings → Actions → General**: allow all actions. Set Workflow permissions to **Read and write**, and tick **Allow GitHub Actions to create and approve pull requests** (the agent opens PRs).
2. Optional: **Settings → Secrets and variables → Actions → New repository secret** `ANTHROPIC_API_KEY`, which lets Claude draft the new date entries.
3. **Actions → update-sources → Run workflow** to test it now. Otherwise it runs daily at 03:00 UTC (08:00 PKT).

**When a PR arrives:** open it and follow the source links. Add or edit the entries in `knowledge/deadlines.yaml` or `knowledge/admissions.yaml` on the same branch (the GitHub web editor works). Merge once the **tests** check passes.

## Phase 10 - Operations: the yearly admission cycle

| When | What to do |
|---|---|
| **Every day (automatic)** | The update agent runs. Review any PR: add new dates (with `link`, `source`, `trust`) to `deadlines.yaml`, then merge. |
| **May-July** (MDCAT/ECAT registration) | Check that the MDCAT and ECAT fees, dates and format in `admissions.yaml → tests` match the new PM&DC / UET notices. Update the `2026` fields to the new year. |
| **July-September** (university advertisements) | Update the UAJK and MUST last dates and merit-list schedule, the new eligibility PDFs (MUST publishes one each Fall), and fee sheets (UAJK notes about 10% yearly increases). Add a new session's fees as a new session value. |
| **After MDCAT results** (Sep-Oct) | Add the AJK MBBS/BDS and SZABMU application windows. When the agent reports **jac.portal: now UP**, update `institutions.yaml → jac.website_status` and the JAC steps. |
| **Each change** | Run `python -m pytest -q`, check the portal locally, then merge. |
| **Once a year** | Review the relaxations (e.g. the 2025-26 MDCAT 52%/47% rule is session-specific), remove expired notes, and rebuild the notebook. |

**Who does what:**
- **The agent:** watch and report.
- **You (or an admission-office volunteer):** verify and edit the YAML.
- **GitHub Actions:** run the agent and the tests.
- **Students:** use the portal or chat.
