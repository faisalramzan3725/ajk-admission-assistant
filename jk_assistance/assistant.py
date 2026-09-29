"""JK Assistance orchestrator (admissions only): route the message, run the admission engines, gather evidence,
and compose the answer (Claude when configured, deterministic markdown otherwise)."""
from __future__ import annotations

import re

from . import advisor, llm
from .config import llm_enabled, today
from .decision import ALERT, ASK_INFO, ESCALATE, GUIDE, OFF_TOPIC, route_message
from .knowledge import get_knowledge

GROUP_WORDS = {
    "pre_med": ["pre-medical", "pre medical", "premedical", "pre-med", "pre med", "fsc medical", "f.sc medical", "pre_med"],
    "pre_eng": ["pre-engineering", "pre engineering", "pre-eng", "pre eng", "fsc engineering", "f.sc engineering", "pre_eng"],
    "ics": ["ics", "i.c.s", "computer science group"],
    "icom": ["i.com", "icom", "commerce group"],
    "fa": ["f.a.", " fa ", "arts group", "humanities", "intermediate arts"],
    "dae": ["dae", "diploma of associate engineer"],
    "a_level": ["a-level", "a level", "a levels"],
    "general_science": ["general science"],
}
NUM = r"(\d{2,4}(?:\.\d+)?)(?:\s*/\s*(\d{2,4}))?\s*(%|percent)?"
ADVICE_WORDS = re.compile(r"eligib|which (university|program|subject|field|course)|where (can|should) i|after (fsc|f\.sc|12|inter|matric)|"
                          r"12th|intermediate|merit|chance|can i (apply|get)|options|want to (study|become|do)|admission in|marks", re.I)
HOWTO_WORDS = re.compile(r"how (to|do i|can i) (apply|enrol|enroll|get admission)|steps|procedure|process|documents?|papers|required|challan|apply", re.I)
DEADLINE_WORDS = re.compile(r"deadline|last date|due date|when (is|are|do|will)|schedule|merit list|dates?", re.I)
TEST_WORDS = re.compile(r"passing|pass(ing)? marks|total marks|out of|how many marks|syllabus|pattern|negative marking|test fee|mcqs?", re.I)


def _score(label_pat: str, t: str):
    m = re.search(label_pat + r"[^0-9]{0,25}" + NUM, t)
    if not m:
        return None
    obt, tot, pct = m.group(1), m.group(2), m.group(3)
    if tot:
        return {"obtained": float(obt), "total": float(tot)}
    return f"{obt}%" if pct else float(obt)


def parse_profile(text: str) -> dict:
    t = " " + text.lower() + " "
    prof: dict = {}
    for g, words in GROUP_WORDS.items():
        if any(w in t for w in words):
            prof["group"] = g
            break
    if (s := _score(r"(?:matric|ssc|10th)", t)) is not None:
        prof["ssc"] = s
    if (h := _score(r"(?:fsc|f\.sc|hssc|inter(?:mediate)?|ics|i\.com|dae|12th|a[- ]level|\bfa\b)", t)) is not None:
        prof["hssc"] = h
    tests = {}
    for tid, pat in (("mdcat", r"mdcat"), ("ecat", r"ecat"), ("must_seet", r"seet"), ("hec_lat", r"\blat\b"), ("uajk_entry_test", r"entry test")):
        if (v := _score(pat, t)) is not None:
            tests[tid] = v
    if tests:
        prof["tests"] = tests
    if "hssc" not in prof:  # a bare percentage like "I got 78%"
        m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:%|percent)", t)
        if m:
            prof["hssc"] = float(m.group(1))
    if re.search(r"(additional|studied|with) math", t):
        prof["studied_math"] = True
    m = re.search(r"(\d{2})\s*(?:years? old|yrs|age)|age\s*(\d{2})", t)
    if m:
        prof["age"] = int(m.group(1) or m.group(2))
    if re.search(r"state subject|ajk domicile|from ajk|azad kashmir domicile", t):
        prof["state_subject"] = True
    interests = advisor.fields_from_text(text)
    if interests:
        prof["interests"] = interests
    named = [i for i, pat in (("uajk", r"(?i)\b(uajk|ajku|ajk university|university of ajk)\b"), ("must", r"\bMUST\b|(?i:\bmirpur university\b)")) if re.search(pat, text)]
    if named:
        prof["institutions"] = named
    return prof


def answer(question: str, profile: dict | None = None) -> dict:
    kb = get_knowledge()
    on = today()
    institution = kb.detect_institution(question)
    test_id = kb.detect_test(question)
    parsed = {**parse_profile(question), **(profile or {})}
    action, intent, structured = GUIDE, "information", {}

    if institution in ("uet", "pmdc") and test_id:  # "ECAT"/"MDCAT" name a test, not where to study
        institution = None
    has_profile = parsed.get("hssc") is not None or parsed.get("group")
    medical = bool({"medicine", "dentistry"} & set(parsed.get("interests") or []))

    forced, why = route_message(question)
    if forced == OFF_TOPIC:
        action, intent = OFF_TOPIC, "off_topic"
        structured = {"message": why, "contacts": _contacts(kb, institution)}
    elif test_id and not has_profile and (TEST_WORDS.search(question) or not (HOWTO_WORDS.search(question) or DEADLINE_WORDS.search(question))):
        intent = "test_info"
        structured = {"test": advisor.test_info(test_id, kb)}
    elif has_profile or (ADVICE_WORDS.search(question) and not HOWTO_WORDS.search(question) and not DEADLINE_WORDS.search(question)):
        intent = "admission_advice"
        res = advisor.advise(parsed, kb, on)
        structured = _trim(res)
        action = ASK_INFO if res.get("needs_info") else GUIDE
    elif DEADLINE_WORDS.search(question):
        intent = "deadlines"
        related = {institution} | ({"pmdc", "pmc"} if institution in ("jac", "szabmu") else set()) if institution else None
        dl = [d for d in advisor.upcoming_deadlines(kb, on, include_past_days=45) if not related or d["institution"] in related]
        structured = {"deadlines": dl}
        action = ALERT if any(0 <= d["days_left"] <= 14 for d in dl) else GUIDE
    elif HOWTO_WORDS.search(question) or institution:
        inst = institution if institution in kb.processes else (
            "jac" if institution in ("pmc", "mbbsmc", "ajkmc", "pmdc", "szabmu") or test_id == "mdcat" or medical else None)
        if inst:
            intent = "how_to_apply"
            structured = {"how_to_apply": advisor.how_to_apply(inst, kb, on)}
        else:
            action, structured = ASK_INFO, {"needs_info": ["institution"],
                                            "message": "Which one - **UAJK** (Muzaffarabad), **MUST** (Mirpur), or **MBBS/BDS** (AJK medical colleges / SZABMU)?"}

    if forced == ESCALATE:
        action = ESCALATE
        structured["escalation_reason"] = why
        structured["contacts"] = _contacts(kb, institution)

    evidence = [{"source": c.source, "trust": c.trust, "text": c.text} for _, c in kb.search(question, institution, k=6)]
    text = llm.compose(question, evidence, structured, action) if llm_enabled() and action != OFF_TOPIC else None
    if not text:
        text = render(intent, action, structured)
    return {"answer": text, "action": action, "intent": intent, "institution": institution, "structured": structured,
            "citations": [{"n": i + 1, "source": e["source"], "trust": e["trust"], "snippet": e["text"][:300]} for i, e in enumerate(evidence)],
            "llm": llm_enabled(), "as_of": on.isoformat()}


def _contacts(kb, institution):
    ids = [institution] if institution in kb.institutions else ["uajk", "must", "pmc"]
    return {kb.institutions[i]["name"]: kb.institutions[i].get("contacts", []) for i in ids}


def _trim(res: dict) -> dict:
    if res.get("needs_info"):
        return res
    ok = [p for p in res["programs"] if p["eligibility"] != "not_eligible"]
    return {**res, "programs": ok[:25], "not_eligible": [{"program": p["program"], "institution": p["institution"],
                                                         "why": [c["criterion"] + ": needs " + c["required"] + ", you have " + str(c["yours"]) for c in p["checks"] if c["status"] == "fail"]}
                                                        for p in res["programs"] if p["eligibility"] == "not_eligible"][:15]}


# ---------------------------------------------------------------------------- deterministic rendering
ICON = {"pass": "✅", "fail": "❌", "pending": "⏳", "check": "⚠️"}
VERDICT = {"eligible": "✅ Eligible", "eligible_after_test": "⏳ Eligible if you pass the entry test", "check_required": "⚠️ Check with the office", "not_eligible": "❌ Not eligible"}


def render(intent: str, action: str, s: dict) -> str:
    out: list[str] = []
    if action == ESCALATE:
        out += [f"**Please contact the admission office.** {s['escalation_reason']}", ""]
        out += _render_contacts(s.get("contacts", {}))
        if intent == "information":
            return "\n".join(out)
        out.append("")
    if action == OFF_TOPIC:
        return "\n".join([s["message"], "", "Try: *I did FSc pre-medical 946/1100, matric 1010/1100, MDCAT 140 - where can I apply?*", ""] + _render_contacts(s.get("contacts", {})))
    if s.get("needs_info"):
        return "\n".join(out + [s["message"], "", "Example: *FSc pre-engineering 880/1100, matric 950/1100, ECAT 220 - I want engineering or computer science.*"])
    if intent == "admission_advice":
        out += render_advice(s)
    elif intent == "test_info":
        out += render_test(s["test"])
    elif intent == "deadlines":
        out += render_deadlines(s["deadlines"])
    elif intent == "how_to_apply":
        out += render_howto(s["how_to_apply"])
    else:
        out += ["I couldn't match this to a specific admission topic. Tell me your intermediate group and marks, or ask e.g. "
                "*How do I apply to UAJK?*, *MDCAT passing marks*, *UAJK last date*. The closest official sources are under Evidence."]
    return "\n".join(out)


def _render_contacts(contacts: dict) -> list[str]:
    lines = []
    for name, rows in contacts.items():
        lines.append(f"- **{name}**: " + "; ".join(f"{r['office']} {r.get('phone', '')} {r.get('email', '')}".strip() for r in rows))
    return lines


def render_advice(s: dict) -> list[str]:
    p = s["profile"]
    tests = ", ".join(f"{k.upper()} {v['percent']:g}%" for k, v in (p.get("tests") or {}).items())
    out = [f"### Your options (group: {p['group']}, HSSC {p['hssc_percent']:g}%" + (f", SSC {p['ssc_percent']:g}%" if p.get("ssc_percent") else "") + (f", {tests}" if tests else "") + ")"]
    if not p.get("interests") and s.get("fields_open_to_you"):
        out.append("**Fields open to you:** " + ", ".join(f"{f['label']} ({f['programs']})" for f in s["fields_open_to_you"]) + ". Tell me which interests you to narrow down.")
    for r in s["programs"][:12]:
        fee = f" · 1st semester Rs. {r['fees']['first_semester']:,} ({r['fees']['session']})" if r.get("fees") else ""
        out.append(f"\n**{r['program']}** - {r['institution'].upper()}, {r['campus']} · {VERDICT[r['eligibility']]} · chance: {r['chance']}{fee}")
        for c in r["checks"]:
            out.append(f"  - {ICON[c['status']]} {c['criterion']}: needs {c['required']} · you: {c['yours']}" + (" *(any one test)*" if c.get("any_of") else "") + (f" - {c['note']}" if c.get("note") else ""))
    if s.get("not_eligible"):
        out.append("\n**Not open to you:** " + "; ".join(f"{n['program'][:50]} ({n['institution'].upper()}: {', '.join(n['why'])[:90]})" for n in s["not_eligible"][:5]))
    for h in s.get("how_to_apply", {}).values():
        out += [""] + render_howto(h, compact=True)
    out.append(f"\n_{s['chance_note']}_")
    return out


def render_test(t: dict) -> list[str]:
    out = [f"### {t['name']}"]
    if t.get("max_marks"):
        out.append(f"**Total marks:** {t['max_marks']}")
    for k, v in (t.get("passing") or {}).items():
        if isinstance(v, dict):
            out.append(f"**Minimum ({k.replace('_', ' ')}):** {v['percent']}%" + (f" = {v['marks']} / {t['max_marks']}" if v.get("marks") else "") + (f" - {v['note']}" if v.get("note") else ""))
        else:
            out.append(f"**Note:** {v}")
    for k in ("format", "conducted_for_ajk_by", "fee", "dates_2026", "use_in_ajk", "note"):
        if t.get(k):
            out.append(f"**{k.replace('_', ' ').capitalize()}:** {t[k]}")
    if t.get("merit_formula"):
        f = t["merit_formula"]
        out.append(f"**Merit formula:** MDCAT {f['mdcat']}% + HSSC {f['hssc']}% + SSC {f['ssc']}%")
    if t.get("reference_averages_fall_2026_first"):
        a = t["reference_averages_fall_2026_first"]
        out.append(f"**Average scores (Fall 2026, first ECAT):** pre-engineering {a['pre_eng']}, ICS {a['ics']}, pre-medical {a['pre_med']} out of 400")
    if t.get("registration") or t.get("portal"):
        out.append(f"**Register:** {t.get('registration') or t.get('portal')}")
    out.append("_Sources: " + ", ".join(t.get("sources", [])) + "_")
    return out


def render_deadlines(dl: list[dict]) -> list[str]:
    if not dl:
        return ["No admission dates on record for this institution in the current period."]
    out = ["### Admission dates"]
    for d in dl:
        when = "passed" if d["days_left"] < 0 else ("today" if d["days_left"] == 0 else f"in {d['days_left']} days")
        out.append(f"- **{d['date']}** ({when}) - {d['title']}" + (" *(third-party source - verify)*" if d.get("trust") == "secondary" else "") + (f". {d['action']}" if d.get("action") else ""))
    return out


def render_howto(h: dict, compact: bool = False) -> list[str]:
    out = [f"#### How to apply - {h['institution']}"]
    if h.get("website_status"):
        out.append(f"> ⚠️ {h['website_status']}")
        out += [f"> - {c}" for c in h.get("working_channels") or []]
    elif h.get("portal"):
        out.append(f"Portal: {h['portal']}")
    out += [f"{i + 1}. **{st['step']}** - {st['detail']}" for i, st in enumerate(h["steps"])]
    if h.get("required_documents"):
        out.append("**Documents:**" if not compact else "**Documents:** " + "; ".join(h["required_documents"]))
        if not compact:
            out += [f"- [ ] {d}" for d in h["required_documents"]]
    upcoming = [d for d in h.get("dates", []) if d["days_left"] >= -7]
    if upcoming:
        out.append("**Dates:** " + "; ".join(f"{d['date']} ({'passed' if d['days_left'] < 0 else str(d['days_left']) + ' days'}) {d['title']}" for d in upcoming))
    if not compact:
        for k in ("age_limit", "reserved_seats", "scholarships", "fee_rules", "refund"):
            if h.get(k):
                out.append(f"**{k.replace('_', ' ').capitalize()}:** {h[k]}")
        if h.get("contacts"):
            out.append("**Contact:** " + "; ".join(f"{c['office']} {c.get('phone', '')}".strip() for c in h["contacts"]))
    return out
