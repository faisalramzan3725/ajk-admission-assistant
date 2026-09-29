"""JK Assistance orchestrator: routes a message to the right engine, gathers evidence, decides the action,
and composes the answer (Claude when configured, deterministic markdown otherwise)."""
from __future__ import annotations

import re

from . import advisor, llm, monitor, store
from .config import llm_enabled, today
from .decision import ALERT, ASK_INFO, ESCALATE, GUIDE, escalate, route_message, triage
from .knowledge import get_knowledge

GROUP_WORDS = {
    "pre_med": ["pre-medical", "pre medical", "premedical", "pre-med", "pre med", "fsc medical", "f.sc medical", "pre_med"],
    "pre_eng": ["pre-engineering", "pre engineering", "pre-eng", "pre eng", "fsc engineering", "f.sc engineering", "pre_eng"],
    "ics": ["ics", "computer science group", "i.c.s"],
    "icom": ["i.com", "icom", "commerce group"],
    "fa": ["f.a", " fa ", "arts group", "humanities", "intermediate arts"],
    "dae": ["dae", "diploma of associate engineer"],
    "a_level": ["a-level", "a level", "a levels"],
    "general_science": ["general science"],
}
ADMISSION_WORDS = re.compile(r"admission|apply|eligib|which (university|program|subject|field)|after (fsc|f\.sc|12|inter|matric)|"
                             r"12th|intermediate|merit|chance|entry test|mdcat|seet|lat\b|want to (study|become|do)|enrol", re.I)
PERSONAL_WORDS = re.compile(r"\bmy\b|\bi am\b|\bam i\b|probation|promot|relegat|dropped|cgpa|gpa|attendance|dues|pending|"
                            r"what if|what happens|semester result", re.I)
DEADLINE_WORDS = re.compile(r"deadline|last date|due date|when (is|are|do)|schedule|merit list", re.I)


def parse_profile(text: str) -> dict:
    t = " " + text.lower() + " "
    prof: dict = {}
    for g, words in GROUP_WORDS.items():
        if any(w in t for w in words):
            prof["group"] = g
            break
    pct = [float(x) for x in re.findall(r"(\d{2,3}(?:\.\d+)?)\s*(?:%|percent|marks)", t)]
    m = re.search(r"mdcat[^0-9]{0,20}(\d{2,3}(?:\.\d+)?)", t)
    if m:
        prof["mdcat_percent"] = float(m.group(1))
    m = re.search(r"(?:matric|ssc)[^0-9]{0,20}(\d{2,3}(?:\.\d+)?)", t)
    if m:
        prof["ssc_percent"] = float(m.group(1))
    m = re.search(r"(?:fsc|f\.sc|hssc|inter(?:mediate)?|ics|fa|i\.com|12th)[^0-9]{0,20}(\d{2,3}(?:\.\d+)?)", t)
    if m:
        prof["hssc_percent"] = float(m.group(1))
    elif pct:
        prof["hssc_percent"] = next((p for p in pct if p not in (prof.get("mdcat_percent"), prof.get("ssc_percent"))), pct[0])
    if "math" in t and ("pre_med" == prof.get("group") or "additional math" in t):
        prof["studied_math"] = True
    interests = advisor.fields_from_text(text)
    if interests:
        prof["interests"] = interests
    # Restrict to one institution only when the student names a university explicitly
    # ("MBBS" also matches JAC as an alias, but "MBBS or DPT" must still show DPT at UAJK/MUST).
    named = [i for i, pat in (("uajk", r"(?i)\b(uajk|ajku|ajk university|university of ajk)\b"), ("must", r"\bMUST\b|(?i:\bmirpur university\b)")) if re.search(pat, text)]
    if named:
        prof["institutions"] = named
    return prof


def answer(question: str, student_id: str | None = None, profile: dict | None = None) -> dict:
    kb = get_knowledge()
    on = today()
    student = store.get("students", student_id) if student_id else None
    institution = kb.detect_institution(question) or (student or {}).get("institution")

    forced_action, forced_why = route_message(question)
    intent, structured, cards = "information", {}, {}
    action = GUIDE

    if student and PERSONAL_WORDS.search(question) and student.get("type") != "applicant":
        intent = "student_status"
        findings = triage(monitor.scan(student), student_id)
        structured = {"student": _student_summary(student), "findings": findings}
        cards["findings"] = findings
        action = findings[0]["action"] if findings else GUIDE
    elif DEADLINE_WORDS.search(question) and not kb.match_services(question, institution) and "hssc_percent" not in parse_profile(question):
        intent = "deadlines"
        dl = [d for d in advisor.upcoming_deadlines(kb, on, include_past_days=30) if not institution or d["institution"] == institution]
        structured = {"deadlines": dl, "rules": [r for r in kb.relative_rules.values() if not institution or r["institution"] == institution]}
        cards["deadlines"] = dl
        action = ALERT if any(0 <= d["days_left"] <= 14 for d in dl) else GUIDE
    elif ADMISSION_WORDS.search(question) and not kb.match_services(question, institution) or profile:
        intent = "admission_advice"
        prof = {**(_applicant_profile(student) if student else {}), **parse_profile(question), **(profile or {})}
        res = advisor.advise(prof, kb, on)
        structured = _trim_advice(res)
        cards["advice"] = structured
        action = ASK_INFO if res.get("needs_info") else GUIDE
    else:
        matches = kb.match_services(question, institution, limit=10)
        top = [m for m in matches if m[0] == matches[0][0]] if matches else []
        if institution is None and len({m[1]["institution"] for m in top}) > 1:
            action = ASK_INFO
            options = {m[1]["institution"]: kb.institutions[m[1]["institution"]]["name"] for m in top}
            structured = {"needs_info": ["institution"], "options": options,
                          "message": "Which institution is this for? " + "; ".join(f"**{k.upper()}** - {v}" for k, v in options.items())}
        elif matches:
            intent = "service"
            svc = matches[0][1]
            structured = {"service": _service_card(svc, kb, on)}
            if len(matches) > 1:
                structured["related_services"] = [m[1]["id"] for m in matches[1:]]
            cards["service"] = structured["service"]
            if svc.get("escalate_when"):
                structured["escalate_when"] = svc["escalate_when"]
        elif institution is None and re.search(r"degree|transcript|dmc|migration|clearance|verification|fee|challan", question, re.I):
            action = ASK_INFO
            structured = {"needs_info": ["institution"], "message": "Which institution - UAJK, MUST, or your medical college (UHS degree)?"}

    if forced_action:
        action = forced_action
        structured["escalation_reason"] = forced_why
        esc = escalate(student_id, question[:120], {"reason": forced_why})
        structured["escalation_id"] = esc["id"]

    evidence = _evidence(question, institution, intent, structured, kb)
    text = llm.compose(question, evidence, structured, action) if llm_enabled() else None
    if not text:
        text = render(intent, action, structured, question)
    return {"answer": text, "action": action, "intent": intent, "institution": institution, "cards": cards,
            "citations": [{"n": i + 1, "source": e["source"], "trust": e["trust"], "snippet": e["text"][:300]} for i, e in enumerate(evidence)],
            "llm": bool(llm_enabled()), "as_of": on.isoformat()}


# ---------------------------------------------------------------------------- helpers
def _service_card(svc: dict, kb, on) -> dict:
    return {"id": svc["id"], "name": svc["name"], "institution": kb.institutions[svc["institution"]]["name"], "office": svc.get("office"),
            "portal": svc.get("portal"), "required_documents": svc.get("required_documents", []), "steps": svc.get("steps", []),
            "fees": kb.service_fees(svc["id"], on), "forms": svc.get("forms", []), "deadlines": svc.get("deadlines", []),
            "processing_time": svc.get("processing_time"), "notes": svc.get("notes", []), "sources": svc.get("sources", []),
            "trust": svc.get("trust", "official")}


def _student_summary(s: dict) -> dict:
    return {k: s.get(k) for k in ("id", "name", "institution", "program", "program_type", "type")}


def _applicant_profile(s: dict) -> dict:
    return {k: s[k] for k in ("group", "hssc_percent", "ssc_percent", "mdcat_percent", "interests", "age", "state_subject", "studied_math")
            if s.get(k) is not None} | ({"institutions": s["target_institutions"]} if s.get("target_institutions") else {})


def _trim_advice(res: dict) -> dict:
    if res.get("needs_info"):
        return res
    eligible = [p for p in res["programs"] if p["eligibility"] != "not_eligible"]
    return {**res, "programs": eligible[:25], "not_eligible_count": len(res["programs"]) - len(eligible)}


def _evidence(question: str, institution, intent: str, structured: dict, kb) -> list[dict]:
    ev, seen = [], set()

    def add(chunk):
        if chunk.id not in seen:
            seen.add(chunk.id)
            ev.append({"id": chunk.id, "source": chunk.source, "trust": chunk.trust, "text": chunk.text})

    by_id = {c.id: c for c in kb.chunks}
    if intent == "service":
        add(by_id[f"service:{structured['service']['id']}"])
    for _, c in kb.search(question, institution, k=5):
        add(c)
    return ev[:6]


# ---------------------------------------------------------------------------- deterministic rendering
def render(intent: str, action: str, s: dict, question: str) -> str:
    lines: list[str] = []
    if action == ESCALATE and s.get("escalation_reason"):
        lines += [f"**This needs a human advisor.** {s['escalation_reason']} (ticket {s.get('escalation_id')}).", ""]
    if s.get("needs_info") and intent != "admission_advice":
        return "\n".join(lines + [s.get("message", "I need a little more information.")])
    if intent == "service":
        lines += render_service(s["service"])
        if s.get("escalate_when"):
            lines += ["", "**Needs an official decision:** " + "; ".join(s["escalate_when"])]
    elif intent == "admission_advice":
        lines += render_advice(s)
    elif intent == "deadlines":
        lines += render_deadlines(s["deadlines"])
    elif intent == "student_status":
        lines += render_findings(s["findings"])
    else:
        lines += ["I could not match this to a specific procedure. The closest official sources are listed below; "
                  "for anything not covered please contact the office named in them."]
    return "\n".join(lines)


def render_service(c: dict) -> list[str]:
    out = [f"### {c['name']} - {c['institution']}"]
    if c.get("office"):
        out.append(f"**Office:** {c['office']}")
    if c.get("portal"):
        out.append(f"**Portal:** {c['portal']}")
    if c["fees"]:
        out.append("\n**Fees (version in force today):**")
        for f in c["fees"]:
            prev = f"; previously Rs. {f['previous_versions'][-1]['amount']:,} from {f['previous_versions'][-1]['effective_from']}" if f.get("previous_versions") else ""
            basis = "as fetched on" if f.get("date_basis") == "fetched" else "effective"
            urgent = f" (urgent Rs. {f['urgent_amount']:,})" if f.get("urgent_amount") else ""
            out.append(f"- {f['item']}: **Rs. {f['amount']:,}**{urgent} - {basis} {f['effective_from']}{prev}")
    if c["required_documents"]:
        out.append("\n**Documents to attach:**")
        out += [f"- [ ] {d}" for d in c["required_documents"]]
    if c["steps"]:
        out.append("\n**Steps:**")
        out += [f"{i + 1}. {st}" for i, st in enumerate(c["steps"])]
    if c.get("processing_time"):
        out.append(f"\n**Processing time:** {c['processing_time']}")
    for d in c.get("deadlines", []):
        out.append(f"\n**Deadline:** {d['rule']}")
    if c.get("forms"):
        out.append("\n**Forms:** " + "; ".join(f"[{f['title']}]({f['url']})" for f in c["forms"] if f.get("url")))
    if c.get("notes"):
        out.append("\n**Notes:** " + " ".join(c["notes"]))
    out.append("\n_Sources: " + ", ".join(c["sources"]) + "_")
    return out


def render_advice(s: dict) -> list[str]:
    if s.get("needs_info"):
        return [s["message"], "", "Example: *I did FSc pre-medical with 82%, matric 88%, MDCAT 71%, I want MBBS or DPT.*"]
    p = s["profile"]
    out = [f"### Programs you can apply for (group: {p.get('group')}, HSSC {p.get('hssc_percent')}%)"]
    for r in s["programs"][:15]:
        fee = ""
        if r.get("fees"):
            fee = f" - 1st semester Rs. {r['fees']['first_semester']:,} ({r['fees'].get('session')})"
            if r["fees"].get("open_merit_first_semester"):
                fee += f", open-merit/self-finance Rs. {r['fees']['open_merit_first_semester']:,}"
        tests = ", ".join(t["name"] for t in r["tests"]) or "no entry test listed"
        mark = "✅" if r["eligibility"] == "eligible" else "⚠️"
        out.append(f"- {mark} **{r['program']}** ({r['institution'].upper()}, {r['campus']}) - chance: {r['chance']}; test: {tests}{fee}")
        for c in r["checks"]:
            out.append(f"    - {c}")
    if s.get("not_eligible_count"):
        out.append(f"\n{s['not_eligible_count']} other program(s) in your areas of interest are not open to your group/marks.")
    for inst, proc in s.get("application_process", {}).items():
        out.append(f"\n**How to apply - {proc['institution']}** ({proc.get('portal', '')})")
        out += [f"{i + 1}. {st}" for i, st in enumerate(proc.get("how_to_apply", []))]
        if proc.get("required_documents"):
            out.append("Documents: " + "; ".join(proc["required_documents"]))
    if s.get("upcoming_deadlines"):
        out.append("\n**Upcoming deadlines:**")
        out += [f"- {d['date']} ({d['days_left']} days): {d['title']}" + (" - *third-party source, verify*" if d.get("trust") == "secondary" else "") for d in s["upcoming_deadlines"]]
    out.append(f"\n_{s['chance_disclaimer']}_")
    return out


def render_deadlines(dl: list[dict]) -> list[str]:
    if not dl:
        return ["No dated deadlines on record for this institution in the coming period."]
    out = ["### Deadlines"]
    for d in dl:
        when = "passed" if d["days_left"] < 0 else ("today" if d["days_left"] == 0 else f"in {d['days_left']} days")
        sec = " *(third-party source - verify)*" if d.get("trust") == "secondary" else ""
        out.append(f"- **{d['date']}** ({when}) - {d['title']}{sec}" + (f". {d['action']}" if d.get("action") else ""))
    return out


def render_findings(findings: list[dict]) -> list[str]:
    if not findings:
        return ["Everything looks on track - no alerts right now."]
    icon = {ESCALATE: "🧑‍💼", ALERT: "⚠️", ASK_INFO: "❓", GUIDE: "ℹ️"}
    out = ["### Your status"]
    for f in findings:
        due = f" (due {f['due_date']}, {f['days_left']} days)" if f.get("due_date") else ""
        out.append(f"- {icon[f['action']]} **{f['action']}** - {f['title']}{due}: {f['detail']}")
    return out
