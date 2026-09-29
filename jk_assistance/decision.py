"""Decision layer: routes each finding (or chat request) to one of four actions.

  GUIDE     - routine, rule-backed information
  ASK_INFO  - the rules can't be applied without more data from the student
  ALERT     - an approaching deadline or an adverse (predicted) consequence
  ESCALATE  - human judgment needed: rules exhausted or unpublished, exceptions, disputes, sensitive situations

Escalations are written to the human-advisor queue (data/escalations.json).
"""
from __future__ import annotations

import re

from . import store
from .config import ALERT_WINDOW_DAYS, today

GUIDE, ASK_INFO, ALERT, ESCALATE = "GUIDE", "ASK_INFO", "ALERT", "ESCALATE"

SENSITIVE = re.compile(r"harass|abuse|suicid|self[- ]harm|depress|mental health|death|died|passed away|pregnan|emergency|"
                       r"threat|bully|discriminat|disciplin|unfair means|cheating case|expel|police|court|legal action|appeal against", re.I)
EXCEPTION = re.compile(r"exception|special case|waive|relax|condon|extension|extend (the )?deadline|appeal|re-?admission|readmission|"
                       r"change my result|grace marks", re.I)


def decide(f: dict) -> dict:
    if f.get("needs_human"):
        action, why = ESCALATE, "The rules do not settle this case or it needs an official decision."
    elif f.get("needs_info"):
        action, why = ASK_INFO, "More information is needed: " + ", ".join(f["needs_info"])
    elif f["severity"] == "critical" or (f["severity"] == "warning" and f.get("days_left") is not None and f["days_left"] <= ALERT_WINDOW_DAYS) \
            or (f["severity"] == "warning" and f.get("days_left") is None):
        action, why = ALERT, "Deadline approaching or an adverse consequence is predicted."
    else:
        action, why = GUIDE, "Routine guidance."
    return {**f, "action": action, "why": why}


def route_message(text: str) -> tuple[str | None, str | None]:
    """Pre-check a chat message: sensitive or exception requests go to a human regardless of what retrieval finds."""
    if SENSITIVE.search(text):
        return ESCALATE, "This involves a sensitive or personal situation - a human advisor should handle it."
    if EXCEPTION.search(text):
        return ESCALATE, "Exceptions, appeals and re-admissions are decided by university officials, not by rules I can apply."
    return None, None


def escalate(student_id: str | None, summary: str, detail: dict | None = None) -> dict:
    row = {"id": store.next_id("escalations", "ESC"), "student_id": student_id, "created_on": today().isoformat(),
           "summary": summary, "detail": detail or {}, "status": "open"}
    return store.append("escalations", row)


def triage(findings: list[dict], student_id: str | None = None, record: bool = True) -> list[dict]:
    decided = [decide(f) for f in findings]
    if record:
        open_summaries = {e["summary"] for e in store.load("escalations") if e.get("student_id") == student_id and e["status"] == "open"}
        for d in decided:
            if d["action"] == ESCALATE and d["title"] not in open_summaries:
                escalate(student_id, d["title"], {"finding": d["code"], "detail": d["detail"]})
    order = {ESCALATE: 0, ALERT: 1, ASK_INFO: 2, GUIDE: 3}
    return sorted(decided, key=lambda d: (order[d["action"]], d.get("days_left", 9999)))
