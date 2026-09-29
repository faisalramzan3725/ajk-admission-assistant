"""Admission advisor for students who have completed 12 years of education.

Given an applicant profile it lists the programs they are eligible for across UAJK, MUST and the AJK medical
colleges (JAC), with the tests, documents, fees, deadlines and application steps for each - plus a clearly
labelled HEURISTIC chance estimate. No institution publishes closing-merit data we could verify, so the chance
band is based only on how far the applicant's marks are above the published minimum and on program demand.
"""
from __future__ import annotations

import re
from datetime import date

from .config import today
from .knowledge import Knowledge, get_knowledge

FIELD_WORDS = {
    "computing": ["computer", "cs", "bscs", "software", "information technology", "ai", "artificial intelligence", "cyber", "data science", "programming", "computing"],
    "engineering": ["engineering", "engineer", "electrical", "mechanical", "civil"],
    "engineering_technology": ["technology", "tech", "biomedical"],
    "medicine": ["mbbs", "doctor", "medicine", "medical"],
    "dentistry": ["bds", "dental", "dentist", "dentistry"],
    "health": ["pharmacy", "pharm", "dpt", "physiotherapy", "physical therapy", "nursing", "allied", "lab", "nutrition", "health", "radiology", "anesthesia"],
    "sciences": ["physics", "chemistry", "math", "mathematics", "statistics", "biology", "botany", "zoology", "biotech", "biotechnology", "geology", "science", "environmental", "forestry", "sports"],
    "social_sciences": ["english", "economics", "sociology", "psychology", "history", "urdu", "islamic", "political", "international relations", "mass communication", "media", "kashmir", "arabic", "tourism"],
    "business": ["bba", "business", "commerce", "accounting", "finance", "banking", "management"],
    "law": ["law", "llb", "lawyer"],
    "education": ["education", "b.ed", "bed", "teaching", "teacher"],
    "arts": ["fine arts", "fashion", "design", "home economics", "bfa"],
}
AGE_LIMITS = {"uajk": 23, "must": 24}
MEDICAL_FIELDS = {"medicine", "dentistry"}


def fields_from_text(text: str) -> list[str]:
    t = text.lower()
    return [f for f, words in FIELD_WORDS.items() if any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t) for w in words)]


def advise(profile: dict, kb: Knowledge | None = None, on: date | None = None) -> dict:
    """profile: {group, hssc_percent, ssc_percent?, mdcat_percent?, interests?: [field or free text], institutions?: [..],
                 age?, state_subject?: bool, studied_math?: bool}"""
    kb = kb or get_knowledge()
    on = on or today()
    group = profile.get("group")
    hssc = profile.get("hssc_percent")
    missing = [k for k in ("group", "hssc_percent") if profile.get(k) in (None, "")]
    if missing:
        return {"needs_info": missing, "message": "Tell me your intermediate group (e.g. pre_med, pre_eng, ics, fa, icom, dae, a_level) and your HSSC percentage."}

    wanted_fields = set()
    for i in profile.get("interests", []) or []:
        wanted_fields.update([i] if i in FIELD_WORDS else fields_from_text(i))
    institutions = set(profile.get("institutions") or [])

    results = []
    for p in kb.programs.values():
        if institutions and p["institution"] not in institutions:
            continue
        if wanted_fields and p["field"] not in wanted_fields:
            continue
        results.append(_assess(p, profile, kb))

    order = {"eligible": 0, "check_required": 1, "not_eligible": 2}
    results.sort(key=lambda r: (order[r["eligibility"]], -r["margin"] if r["margin"] is not None else 0))
    inst_ids = sorted({r["institution"] for r in results})
    return {
        "profile": profile,
        "as_of": on.isoformat(),
        "programs": results,
        "application_process": {i: _process(kb, i) for i in inst_ids},
        "upcoming_deadlines": [d for d in upcoming_deadlines(kb, on, audience="applicants") if d["institution"] in inst_ids or not inst_ids],
        "chance_disclaimer": ("Chance bands are a heuristic based on your margin over the published minimum and program demand. "
                              "Actual selection depends on the entry test, the merit formula and closing merit of the year, "
                              "which the institutions do not publish in a verifiable form."),
    }


def _assess(p: dict, profile: dict, kb: Knowledge) -> dict:
    group, hssc = profile["group"], float(profile["hssc_percent"])
    reasons, checks = [], []
    status = "eligible"

    if group not in p["groups"]:
        status = "not_eligible"
        reasons.append(f"Requires one of: {', '.join(kb.admissions['groups'].get(g, g) for g in p['groups'])}.")
    if p.get("math_required") and group in {"pre_med", "fa", "icom"} and not profile.get("studied_math"):
        if status == "eligible":
            status = "check_required"
        checks.append("Requires Mathematics at intermediate level - eligible only if you studied Mathematics (e.g. additional Math).")
    if p.get("math_note") and group in {"pre_med", "fa", "icom"} and not profile.get("studied_math"):
        checks.append(p["math_note"])

    margin = None
    if p.get("min_percent") is None:
        if status == "eligible":
            status = "check_required"
        checks.append("Minimum marks are not published - confirm with the admission office.")
    else:
        margin = round(hssc - p["min_percent"], 1)
        if margin < 0:
            status = "not_eligible"
            reasons.append(f"Minimum {p['min_percent']}% in HSSC required; you have {hssc}%.")

    age, limit = profile.get("age"), AGE_LIMITS.get(p["institution"])
    if age and limit and age > limit:
        status = "not_eligible" if status == "eligible" else status
        reasons.append(f"Upper age limit {limit} years at {p['institution'].upper()} (you entered {age}).")

    aggregate = None
    if p["field"] in MEDICAL_FIELDS:
        if profile.get("state_subject") is False:
            checks.append("AJK-national seats need a First Class State Subject; other categories (overseas, foreign, refugee) have separate rules - ask JAC.")
            status = "check_required" if status == "eligible" else status
        mdcat = profile.get("mdcat_percent")
        if mdcat is None:
            checks.append(f"MDCAT required (minimum {p.get('mdcat_min')}%). Enter your MDCAT % to compute the merit aggregate.")
            status = "check_required" if status == "eligible" else status
        else:
            if mdcat < p.get("mdcat_min", 0):
                status = "not_eligible"
                reasons.append(f"MDCAT minimum {p['mdcat_min']}%; you have {mdcat}%.")
            f = p.get("merit_formula") or {}
            if profile.get("ssc_percent") is not None and f:
                aggregate = round(f["ssc"] / 100 * profile["ssc_percent"] + f["hssc"] / 100 * hssc + f["mdcat"] / 100 * mdcat, 2)

    tests = [dict(id=t, **kb.admissions["tests"][t]) for t in p.get("tests", [])]
    return {
        "id": p["id"], "institution": p["institution"], "institution_name": kb.institutions[p["institution"]]["name"],
        "program": p["name"], "campus": p.get("campus"), "field": p["field"], "years": p.get("years"),
        "eligibility": status, "reasons": reasons, "checks": checks + ([p["note"]] if p.get("note") else []),
        "margin": margin, "chance": _chance(status, margin, p, aggregate), "merit_aggregate": aggregate,
        "tests": tests, "fees": p.get("fees"),
    }


def _chance(status: str, margin: float | None, p: dict, aggregate: float | None) -> str:
    if status == "not_eligible":
        return "not eligible"
    if p["field"] in MEDICAL_FIELDS:
        return ("unknown - no verified closing merit; your aggregate is " + str(aggregate)) if aggregate is not None else "unknown - needs MDCAT and SSC marks"
    if margin is None:
        return "unknown - minimum marks not published"
    bands = [(10, "low to moderate"), (20, "moderate"), (999, "good")] if p.get("demand") == "high" else [(5, "moderate"), (15, "good"), (999, "strong")]
    for cut, label in bands:
        if margin < cut:
            return label + " (heuristic)"
    return "good (heuristic)"


def _process(kb: Knowledge, inst: str) -> dict:
    key = "jac_medical" if inst == "jac" else inst
    proc = kb.admissions["application_process"].get(key, {})
    return {"institution": kb.institutions[inst]["name"], **proc}


def upcoming_deadlines(kb: Knowledge, on: date, audience: str | None = None, include_past_days: int = 0) -> list[dict]:
    out = []
    for d in kb.dated_deadlines:
        dd = d["date"] if isinstance(d["date"], date) else date.fromisoformat(str(d["date"]))
        days = (dd - on).days
        if days < -include_past_days or (audience and d.get("audience") != audience):
            continue
        out.append({**d, "date": dd.isoformat(), "days_left": days})
    return sorted(out, key=lambda x: x["date"])
