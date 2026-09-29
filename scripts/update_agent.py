"""JK Assistance update agent - keeps the admission knowledge fresh.

Runs on a schedule (GitHub Actions, see .github/workflows/update-sources.yml) or by hand:

    python scripts/update_agent.py            # full run
    python scripts/update_agent.py --no-llm   # skip the optional Claude step
    python scripts/update_agent.py --only uajk.admission_procedure pmdc.home

Phases of one run:
  1. FETCH     every source in knowledge/sources.yaml (reachability recorded, incl. sites that are down such as JAC)
  2. DIFF      compare the page text with the previous run (knowledge/source_state.json); save fresh text to raw/<site>/
  3. DETECT    in the ADDED lines: dates, rupee amounts, percentages/marks rules, new PDF/notice links
  4. LINKS     health-check every link a student is shown (date links, portals) - catches another "JAC is down"
  5. CALENDAR  flag institutions with no upcoming date (the calendar needs the next admission cycle)
  6. PROPOSE   (optional, needs ANTHROPIC_API_KEY) Claude reads changed pages and drafts new deadline entries as JSON
  7. REPORT    reports/update_report.md + reports/proposals.json; exit flag "changed" for the workflow

The agent NEVER edits knowledge/admissions.yaml or deadlines.yaml itself: fees, dates and eligibility rules are
official facts, so a person reviews the report/PR and applies the change. That keeps every answer traceable.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from jk_assistance.advisor import upcoming_deadlines  # noqa: E402
from jk_assistance.config import today  # noqa: E402
from jk_assistance.knowledge import get_knowledge  # noqa: E402
from jk_assistance.sources import document_links, fetch, page_text, slug  # noqa: E402

STATE = ROOT / "knowledge" / "source_state.json"
REPORTS = ROOT / "reports"
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATE_RE = re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?[\s\-/,]+(?:{MONTHS})[a-z]*[\s\-/,]+\d{{4}}\b|\b(?:{MONTHS})[a-z]*\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b|\b\d{{1,2}}[-/.]\d{{1,2}}[-/.]20\d\d\b", re.I)
FEE_RE = re.compile(r"(?:rs\.?|pkr)\s*[\d,]{3,}", re.I)
RULE_RE = re.compile(r"[^.\n]{0,80}\b\d{2}(?:\.\d+)?\s?%[^.\n]{0,80}|[^.\n]{0,60}\b(?:minimum|at least|passing)\b[^.\n]{0,80}", re.I)
KEYWORDS = re.compile(r"admission|last date|merit list|deadline|apply|mdcat|ecat|entry test|result|closing|extended", re.I)


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def run(only: list[str] | None, use_llm: bool) -> dict:
    sources = yaml.safe_load((ROOT / "knowledge" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    if only:
        sources = [s for s in sources if s["id"] in only]
    state, now = load_state(), datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = {"run_at": now, "today": today().isoformat(), "sources": [], "changes": [], "status_changes": [],
              "new_documents": [], "link_problems": [], "calendar_gaps": [], "proposals": []}

    # ---------------- 1-3. FETCH, DIFF, DETECT
    for s in sources:
        prev = state.get(s["id"], {})
        res = fetch(s["url"])
        entry = {"id": s["id"], "url": s["url"], "ok": res["ok"], "status": res["status"], "error": res["error"]}
        report["sources"].append(entry)
        if prev and prev.get("ok") != res["ok"]:
            report["status_changes"].append({**entry, "was_ok": prev.get("ok")})
        new_state = {"ok": res["ok"], "status": res["status"], "checked": now, "hash": prev.get("hash"), "docs": prev.get("docs", [])}
        if res["ok"] and "status" not in s["watch"]:
            text = page_text(res["html"])
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            docs = [u for _, u in document_links(res["html"], s["url"])]
            if prev.get("hash") and h != prev["hash"]:
                old_file = ROOT / "raw" / s["site"] / f"{slug(s['url'])}.txt"
                old = old_file.read_text(encoding="utf-8", errors="ignore").split("\n", 2)[-1] if old_file.exists() else ""
                added = [l[1:].strip() for l in difflib.unified_diff(old.splitlines(), text.splitlines(), lineterm="", n=0)
                         if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
                added_text = "\n".join(added)
                report["changes"].append({
                    "id": s["id"], "url": s["url"], "added_lines": len(added),
                    "dates": sorted(set(DATE_RE.findall(added_text)))[:20] if "dates" in s["watch"] else [],
                    "fees": sorted(set(FEE_RE.findall(added_text)))[:20] if "fees" in s["watch"] else [],
                    "rules": [m.strip() for m in RULE_RE.findall(added_text)][:10] if "rules" in s["watch"] else [],
                    "admission_lines": [l for l in added if KEYWORDS.search(l)][:15],
                    "sample": added[:8]})
            if "links" in s["watch"] and prev.get("docs") is not None:
                for u in sorted(set(docs) - set(prev.get("docs", []))):
                    if prev.get("hash"):  # only after the first baseline run
                        report["new_documents"].append({"source": s["id"], "url": u})
            new_state.update(hash=h, docs=docs)
            out = ROOT / "raw" / s["site"]
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{slug(s['url'])}.txt").write_text(f"SOURCE: {s['url']}\n\n{text}", encoding="utf-8")
        state[s["id"]] = new_state

    # ---------------- 4. LINKS shown to students
    kb = get_knowledge()
    links = {d["link"] for d in kb.dated_deadlines if str(d.get("link", "")).startswith("http")}
    links |= {i.get("admission_portal") for i in kb.institutions.values() if i.get("admission_portal")}
    for u in sorted(links):
        res = fetch(u, timeout=25)
        if not res["ok"]:
            report["link_problems"].append({"url": u, "error": res["error"] or res["status"]})

    # ---------------- 5. CALENDAR freshness
    upcoming = upcoming_deadlines(kb, today())
    for inst in ("uajk", "must", "jac", "pmdc"):
        if not any(d["institution"] == inst for d in upcoming):
            report["calendar_gaps"].append(inst)

    # ---------------- 6. PROPOSE (optional Claude step)
    if use_llm and os.environ.get("ANTHROPIC_API_KEY") and report["changes"]:
        report["proposals"] = propose_with_claude(report["changes"])

    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    report["changed"] = bool(report["changes"] or report["status_changes"] or report["new_documents"])
    write_report(report)
    return report


def propose_with_claude(changes: list[dict]) -> list[dict]:
    """Ask Claude to turn changed admission text into draft deadlines.yaml entries (validated JSON). Drafts only."""
    import anthropic
    from pydantic import BaseModel

    class Proposal(BaseModel):
        institution: str
        title: str
        date: str  # YYYY-MM-DD
        link: str
        evidence_quote: str
        confidence: str  # high | medium | low

    class Proposals(BaseModel):
        proposals: list[Proposal]

    text = "\n\n".join(f"SOURCE {c['url']} (id {c['id']}):\n" + "\n".join(c["admission_lines"] or c["sample"]) for c in changes)[:30000]
    try:
        resp = anthropic.Anthropic().messages.parse(
            model=os.environ.get("JK_MODEL", "claude-opus-5-5"),
            max_tokens=16000,
            messages=[{"role": "user", "content":
                       "These lines were newly added to official admission web pages in Azad Jammu & Kashmir (UAJK, MUST, PM&DC, "
                       "SZABMU, Poonch Medical College). Extract ONLY admission dates that are explicitly stated (last dates, "
                       "extensions, merit lists, test dates, registration windows). Use institution ids uajk, must, pmdc, szabmu, pmc. "
                       "Quote the exact supporting text. Do not guess years or dates. If none, return an empty list.\n\n" + text}],
            output_format=Proposals,
        )
        return [p.model_dump() for p in resp.parsed_output.proposals]
    except anthropic.APIError as e:
        return [{"error": f"Claude step failed: {type(e).__name__}"}]


def write_report(r: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "proposals.json").write_text(json.dumps(r["proposals"], indent=1, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for s in r["sources"] if s["ok"])
    L = [f"# JK Assistance - source update report", "", f"Run at {r['run_at']} (today = {r['today']}). "
         f"Sources reachable: **{ok} / {len(r['sources'])}**.", ""]
    if r["status_changes"]:
        L += ["## Reachability changed", ""] + [f"- **{s['id']}** {s['url']}: now {'UP' if s['ok'] else 'DOWN (' + str(s['error']) + ')'}" for s in r["status_changes"]] + [""]
    if r["changes"]:
        L += ["## Pages that changed", ""]
        for c in r["changes"]:
            L += [f"### {c['id']} - {c['url']}", f"{c['added_lines']} new line(s)."]
            for k in ("dates", "fees", "rules", "admission_lines"):
                if c[k]:
                    L.append(f"- **{k.replace('_', ' ')}:** " + " | ".join(c[k]))
            L.append("")
    if r["new_documents"]:
        L += ["## New documents / notices linked", ""] + [f"- ({d['source']}) {d['url']}" for d in r["new_documents"]] + [""]
    if r["proposals"]:
        L += ["## Draft deadline entries (Claude) - verify before adding to knowledge/deadlines.yaml", "", "```json",
              json.dumps(r["proposals"], indent=1, ensure_ascii=False), "```", ""]
    if r["link_problems"]:
        L += ["## Links shown to students that failed", ""] + [f"- {p['url']}: {p['error']}" for p in r["link_problems"]] + [""]
    if r["calendar_gaps"]:
        L += ["## Calendar needs the next cycle", "", "No upcoming admission date on record for: **" + ", ".join(r["calendar_gaps"]) + "**. "
              "Check the changed pages above and add the new dates to knowledge/deadlines.yaml.", ""]
    L += ["## All sources", "", "| id | reachable | status |", "|---|---|---|"] + \
         [f"| {s['id']} | {'yes' if s['ok'] else 'NO'} | {s['status'] or s['error']} |" for s in r["sources"]]
    if not r["changed"]:
        L.insert(4, "**No content changes since the last run.**\n")
    (REPORTS / "update_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    rep = run(a.only, use_llm=not a.no_llm)
    print(f"sources ok: {sum(s['ok'] for s in rep['sources'])}/{len(rep['sources'])} | changed pages: {len(rep['changes'])} | "
          f"reachability changes: {len(rep['status_changes'])} | new documents: {len(rep['new_documents'])} | "
          f"broken student links: {len(rep['link_problems'])} | calendar gaps: {rep['calendar_gaps']}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if rep['changed'] else 'false'}\n")
