# AJK Assistance

**An admission assistant for students in Azad Jammu & Kashmir who have just finished 12 years of education and don't know where to go, whether they are eligible, or how to apply.**

A student enters their intermediate group, their marks (obtained / out of) and any entry-test scores. JK Assistance then:

- lists every program they can apply to at **UAJK** (Muzaffarabad), **MUST** (Mirpur), the **AJK public medical colleges** (AJKMC, MBBSMC, Poonch Medical College) and the **SZABMU federal medical colleges** (which have AJK-quota seats);
- shows an **eligibility checklist** for each program, e.g. *MDCAT needs ≥ 55% = 99 / 180, you have 140 / 180 = 77.78% *;
- computes the **MBBS/BDS merit aggregate** (PM&DC formula: MDCAT 50% + HSSC 40% + SSC 10%);
- gives a clearly labelled **heuristic chance**, first-semester **fees**, and **seats**;
- explains **how to apply step by step**, with the document checklist, contacts and **admission dates** (with days left).

| Entry test | Max marks | Minimum |
|---|---|---|
| MDCAT (PM&DC) | **180** (no negative marking) | MBBS **99** (55%) · BDS **90** (50%) |
| ECAT (UET) | **400** (100 MCQs × 4, negative marking) | PEC engineering **132** (33%) |
| MUST SEET | shown on result card | 33% (engineering) |
| UAJK entry test | shown on result card | 50% |
| HEC LAT (law) | shown on result card | 50% (UAJK LLB) |

**The JAC website (jac.ajk.gov.pk) is not working** (403 / Cloudflare block). JK Assistance uses these official, working channels instead:

- **PM&DC**: the regulator, for eligibility, MDCAT marks and the merit formula;
- **SZABMU Islamabad**: it conducts MDCAT for AJK and runs the federal colleges with AJK-quota seats;
- **the AJK medical colleges' admission cells**: Poonch Medical College 05824-960065, MBBSMC 05827-920453.

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python -m uvicorn jk_assistance.api:app --port 8010
```

Open http://localhost:8010. The tabs are: **1. Find my programs**, **2. How to apply**, **Entry tests**, **Admission dates**, **Ask a question**.

Optional: set `ANTHROPIC_API_KEY` (see `.env.example`) so Claude (`claude-opus-5-5`) writes the chat answers. Eligibility, marks, fees and dates always come from the rule engine.

## Use it from Claude (MCP)

```bash
python mcp_server/server.py
```

Tools: `check_admission`, `get_test`, `how_to_apply`, `admission_dates`, `list_programs`, `search_admission_sources`, `ask_jk_assistance`. See [mcp_server/README.md](mcp_server/README.md).

## Test

```bash
python -m pytest -q
```

The 49 tests cover:
- marks parsing (percent, obtained/out of, raw MDCAT/ECAT scores);
- the official test facts;
- MBBS/BDS and ECAT/SEET eligibility, including the "any one test" logic;
- the Mathematics requirement and age limits;
- the merit aggregate;
- chat routing (including the off-topic and escalation cases);
- the JAC replacement channels, YAML integrity and the API.

Sample notebook with executed outputs: [notebooks/JK_Assistance_Samples.ipynb](notebooks/JK_Assistance_Samples.ipynb). To rebuild it:

```bash
python scripts/build_notebook.py
```

## Automatic updates

An **update agent** (`scripts/update_agent.py`) runs daily through GitHub Actions. It re-checks 23 official sources and detects new dates, fees, rules, notices and dead links. When something changes it opens a pull request with a report, and a person verifies and merges. Setup steps are in [docs/PHASES.md](docs/PHASES.md), Phase 9.

## Documentation

| Document | Contents |
|---|---|
| [docs/JK_Assistance_Guide.pdf](docs/JK_Assistance_Guide.pdf) | **Beginner PDF guide**: how it works, user manual, building an agent from scratch (step-by-step with code), and 25 interview questions with model answers. Rebuild with `python scripts/build_guide_pdf.py` |
| [docs/PHASES.md](docs/PHASES.md) | **Complete documentation, phase by phase**: data collection, extraction, knowledge, retrieval, eligibility engine, chat, interfaces, testing, update agent, yearly operations |
| [docs/MANUAL.md](docs/MANUAL.md) | Install, localhost, portal walkthrough, REST API, MCP, testing, how the assistant works, implementation, updating data |
| [knowledge/README.md](knowledge/README.md) | Sources, trust levels, known gaps, how to update |
| [mcp_server/README.md](mcp_server/README.md) | MCP tools and client configuration |

## Layout Structure

```
jk_assistance/   knowledge.py (index) · advisor.py (eligibility engine) · assistant.py (chat router) · decision.py · llm.py · api.py
knowledge/       institutions.yaml · admissions.yaml (tests, programs, how to apply) · deadlines.yaml
web/index.html   the admission portal
mcp_server/      MCP server
documents/, raw/ official admission sources (PDFs, pages) + extracted text
notebooks/       executed samples
scripts/         data collection, notebook builder, MCP smoke test
tests/           pytest suite
```

## Limitations

- Data retrieved **2026-09-29**. UAJK fees are for sessions starting 2025 (UAJK notes about 10% annual increases); MUST fees are from its 2024-25 prospectus.
- **No university publishes verified closing merits**, so "chance" is a heuristic. For ECAT it compares your score with UET's official Fall 2026 group averages.
- The AJK MBBS application window and fee for the next session were not published at the time of retrieval, because the JAC site is down. Last cycle's details come from a third-party site and are marked "verify".
- Whether MUST accepts ECAT (as a PEC-approved test) must be confirmed with MUST's DSA; the tool says so.
