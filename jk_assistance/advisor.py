"""Admission advisor for students who have completed 12 years of education.

Input (all marks may be given as a percentage or as {"obtained": x, "total": y}):
  group, ssc, hssc, tests: {mdcat: 140 | {obtained, total}, ecat: ..., uajk_entry_test: ..., must_seet: ..., hec_lat: ...},
  interests, institutions, age, state_subject, studied_math

Output: every matching program with an explicit eligibility checklist (criterion / required / yours / status),
the PM&DC merit aggregate for MBBS/BDS, a clearly labelled heuristic chance, fees, and the step-by-step
application process + upcoming dates for each institution.
"""
from __future__ import annotations

import re
from datetime import date

from .config import today
from .knowledge import Knowledge, get_knowledge

FIELD_WORDS = {
    "computing": ["computer", "cs", "bscs", "software", "information technology", "ai", "artificial intelligence", "cyber", "data science", "programming", "computing"],
    "engineering": ["engineering", "engineer", "electrical", "mechanical", "civil"],
    "engineering_technology": ["engineering technology", "technology", "biomedical"],
    "medicine": ["mbbs", "doctor", "medicine", "medical"],
    "dentistry": ["bds", "dental", "dentist", "dentistry"],
    "health": ["pharmacy", "pharm", "pharm-d", "dpt", "physiotherapy", "physical therapy", "nursing", "allied", "lab", "nutrition", "health", "radiology", "anesthesia"],
    "sciences": ["physics", "chemistry", "math", "mathematics", "statistics", "biology", "botany", "zoology", "biotech", "biotechnology", "geology", "science", "environmental", "forestry", "sports"],
    "social_sciences": ["english", "economics", "sociology", "psychology", "history", "urdu", "islamic", "political", "international relations", "mass communication", "media", "kashmir", "arabic", "tourism"],
    "business": ["bba", "business", "commerce", "accounting", "finance", "banking", "management"],
    "law": ["law", "llb", "lawyer"],
    "education": ["education", "b.ed", "bed", "teaching", "teacher"],
    "arts": ["fine arts", "fashion", "design", "home economics", "bfa"],
}
FIELD_LABELS = {"computing": "Computing / IT / AI", "engineering": "Engineering", "engineering_technology": "Engineering Technology",
                "medicine": "Medicine (MBBS)", "dentistry": "Dentistry (BDS)", "health": "Health sciences (DPT, Pharm-D, nursing, allied)",
                "sciences": "Natural sciences", "social_sciences": "Social sciences & languages", "business": "Business & commerce",
                "law": "Law", "education": "Education", "arts": "Arts & design"}
AGE_LIMITS = {"uajk": 23, "must": 24}
MEDICAL = {"medicine", "dentistry"}
PASS, FAIL, PENDING, CHECK = "pass", "fail", "pending", "check"


def fields_from_text(text: str) -> list[str]:
    """Fields mentioned in the text, in the order the student mentioned them. Group names such as
    'pre-medical' or 'pre-engineering' describe what the student studied, not what they want - they are masked."""
    t = re.sub(r"pre[- ]?(medical|med|engineering|eng)\b|f\.?sc\.? (medical|engineering)|computer science group|general science",
               lambda m: " " * len(m.group(0)), text.lower())
    found = {}
    for f, words in FIELD_WORDS.items():
        positions = [m.start() for w in words for m in [re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t)] if m]
        if positions:
            found[f] = min(positions)
    return sorted(found, key=found.get)


def to_percent(v, default_total: float | None = None) -> float | None:
    """Accept 78.5, '78.5%', '946/1100', {'obtained': 946, 'total': 1100} or {'obtained': 140} with a default total."""
    if v in (None, "", {}):
        return None
    if isinstance(v, dict):
        obt, tot = v.get("obtained"), v.get("total") or default_total
        return round(float(obt) / float(tot) * 100, 2) if obt not in (None, "") and tot else None
    if isinstance(v, str):
        m = re.match(r"\s*([\d.]+)\s*/\s*([\d.]+)", v)
        if m:
            return round(float(m.group(1)) / float(m.group(2)) * 100, 2)
        if v.strip().endswith("%"):
            return float(v.strip().rstrip("%"))
        v = float(v)
    v = float(v)
    if default_total:  # tests with a fixed maximum: a bare number is marks obtained (MDCAT 95 = 95/180)
        return round(v / default_total * 100, 2)
    return v


def _marks(percent: float, total) -> str:
    return f"{percent:g}% = {round(percent / 100 * total + 1e-9, 1):g} / {total}" if total else f"{percent:g}%"


def normalize(profile: dict, kb: Knowledge) -> dict:
    p = dict(profile)
    p["ssc_percent"] = to_percent(p.get("ssc", p.get("ssc_percent")))
    p["hssc_percent"] = to_percent(p.get("hssc", p.get("hssc_percent")))
    tests = {}
    for tid, val in (p.get("tests") or {}).items():
        mx = kb.tests.get(tid, {}).get("max_marks")
        pct = to_percent(val, mx)
        if pct is not None:
            obt = val.get("obtained") if isinstance(val, dict) else (float(val) if mx and not str(val).strip().endswith("%") else None)
            tot = (val.get("total") if isinstance(val, dict) else None) or mx
            tests[tid] = {"percent": pct, "obtained": obt, "total": tot}
    if p.get("mdcat_percent") is not None and "mdcat" not in tests:  # backwards-compatible shortcut
        tests["mdcat"] = {"percent": float(p["mdcat_percent"]), "obtained": None, "total": 180}
    p["tests"] = tests
    return p


def advise(profile: dict, kb: Knowledge | None = None, on: date | None = None) -> dict:
    kb = kb or get_knowledge()
    on = on or today()
    p = normalize(profile, kb)
    missing = [k for k, v in (("group", p.get("group")), ("hssc", p.get("hssc_percent"))) if v in (None, "")]
    if missing:
        return {"needs_info": missing, "message": "Tell me your intermediate group (pre_med, pre_eng, ics, fa, icom, general_science, dae, a_level) "
                                                  "and your HSSC marks (e.g. 946/1100 or 86%)."}

    wanted: list[str] = []  # keeps the student's order of preference
    for i in p.get("interests") or []:
        wanted += [f for f in ([i] if i in FIELD_WORDS else fields_from_text(i)) if f not in wanted]
    institutions = set(p.get("institutions") or [])
    open_fields: dict[str, int] = {}
    results = []
    for prog in kb.programs.values():
        if institutions and prog["institution"] not in institutions:
            continue
        r = assess(prog, p, kb)
        if r["eligibility"] != "not_eligible":
            open_fields[prog["field"]] = open_fields.get(prog["field"], 0) + 1
        if wanted and prog["field"] not in wanted:
            continue
        results.append(r)

    # open programs first, then the student's own order of interests, then readiness, then margin
    order = {"eligible": 0, "eligible_after_test": 1, "check_required": 2, "not_eligible": 3}
    results.sort(key=lambda r: (r["eligibility"] == "not_eligible", wanted.index(r["field"]) if r["field"] in wanted else 0,
                                order[r["eligibility"]], -(r["margin"] or 0)))
    inst_ids = sorted({r["institution"] for r in results if r["eligibility"] != "not_eligible"})
    return {
        "as_of": on.isoformat(),
        "profile": {k: p.get(k) for k in ("group", "ssc_percent", "hssc_percent", "tests", "interests", "institutions", "age", "state_subject", "studied_math")},
        "fields_open_to_you": [{"field": f, "label": FIELD_LABELS[f], "programs": n} for f, n in sorted(open_fields.items(), key=lambda x: -x[1])],
        "programs": results,
        "how_to_apply": {i: how_to_apply(i, kb, on) for i in inst_ids},
        "chance_note": ("'Chance' is a heuristic from your margin above the published minimum and how competitive the program is. "
                        "No university publishes verified closing merits; final selection depends on the merit list of the year."),
    }


def assess(prog: dict, p: dict, kb: Knowledge) -> dict:
    group, hssc = p["group"], p["hssc_percent"]
    checks = []

    def add(criterion, required, yours, status, note=None):
        checks.append({"criterion": criterion, "required": required, "yours": yours, "status": status, **({"note": note} if note else {})})

    group_names = ", ".join(kb.groups.get(g, g) for g in prog["groups"])
    add("Intermediate group", group_names, kb.groups.get(group, group), PASS if group in prog["groups"] else FAIL)

    margin = None
    if prog.get("min_percent") is None:
        add("HSSC marks", "not published", f"{hssc:g}%", CHECK, "Ask the admission office for the minimum.")
    else:
        margin = round(hssc - prog["min_percent"], 2)
        add("HSSC marks", f"≥ {prog['min_percent']}%", f"{hssc:g}%", PASS if margin >= 0 else FAIL)

    if prog.get("math_required") and group in {"pre_med", "fa", "icom"}:
        add("Intermediate Mathematics", "required", "yes" if p.get("studied_math") else "not studied", PASS if p.get("studied_math") else FAIL)
    if prog.get("math_note") and group in {"pre_med", "fa", "icom"} and not p.get("studied_math"):
        add("Mathematics", "deficiency courses", "not studied", CHECK, prog["math_note"])

    rules = prog.get("test_rules") or []
    for rule in rules:  # the student needs ANY one of these tests
        t = kb.tests[rule["test"]]
        got = p["tests"].get(rule["test"])
        if got is None:
            st, yours = PENDING, "not entered / not taken yet"
        else:
            yours = (f"{got['obtained']:g} / {got['total']:g} = " if got.get("obtained") is not None and got.get("total") else "") + f"{got['percent']:g}%"
            st = PASS if got["percent"] >= rule["min_percent"] else FAIL
        add(t["name"], f"≥ {_marks(rule['min_percent'], t.get('max_marks'))}", yours, st,
            "Confirm with the university that this test is accepted." if rule.get("confirm") else None)
        checks[-1]["any_of"] = len(rules) > 1

    age, limit = p.get("age"), AGE_LIMITS.get(prog["institution"])
    if age and limit:
        add("Age at closing date", f"≤ {limit} years", f"{age}", PASS if age <= limit else FAIL)
    if prog.get("state_subject_required"):
        ss = p.get("state_subject")
        add("AJK State Subject (Class-I)", "required for AJK-national seats", {True: "yes", False: "no", None: "not stated"}[ss],
            PASS if ss else (FAIL if ss is False else CHECK), None if ss else "Overseas/foreign/refugee categories have separate rules.")
    if prog.get("domicile_proof_required"):
        add("Domicile + proof of residence", "AJK domicile for the AJK-quota seats", "bring proof", CHECK)

    verdict = _verdict(checks)
    aggregate = None
    f = prog.get("merit_formula")
    if f and "mdcat" in p["tests"] and p.get("ssc_percent") is not None:
        aggregate = round(f["mdcat"] / 100 * p["tests"]["mdcat"]["percent"] + f["hssc"] / 100 * hssc + f["ssc"] / 100 * p["ssc_percent"], 3)
    return {
        "id": prog["id"], "institution": prog["institution"], "institution_name": kb.institutions[prog["institution"]]["name"],
        "program": prog["name"], "campus": prog.get("campus"), "field": prog["field"], "years": prog.get("years"),
        "eligibility": verdict, "checks": checks, "margin": margin, "merit_aggregate": aggregate,
        "chance": _chance(verdict, margin, prog, aggregate, p, kb), "fees": prog.get("fees"), "seats": prog.get("seats"), "note": prog.get("note"),
    }


def _verdict(checks: list[dict]) -> str:
    plain = [c for c in checks if not c.get("any_of")]
    anyof = [c for c in checks if c.get("any_of")]
    if any(c["status"] == FAIL for c in plain):
        return "not_eligible"
    test_status = None
    if anyof:
        sts = {c["status"] for c in anyof}
        test_status = PASS if PASS in sts else (PENDING if PENDING in sts else FAIL)
    if test_status == FAIL:
        return "not_eligible"
    if any(c["status"] == PENDING for c in plain) or test_status == PENDING:
        return "eligible_after_test"
    if any(c["status"] == CHECK for c in plain):
        return "check_required"
    return "eligible"


def _chance(verdict, margin, prog, aggregate, p, kb) -> str:
    if verdict == "not_eligible":
        return "not eligible"
    if prog["field"] in MEDICAL:
        if aggregate is None:
            return "enter SSC, HSSC and MDCAT marks to compute your merit aggregate"
        return f"merit aggregate {aggregate}% - public-college merit is very competitive and closing merits are not published; apply to all options"
    ecat = p["tests"].get("ecat")
    if ecat and any(r["test"] == "ecat" for r in prog.get("test_rules") or []) and ecat.get("obtained") is not None:
        avg = kb.tests["ecat"]["reference_averages_fall_2026_first"].get(p["group"])
        if avg:
            rel = "above" if ecat["obtained"] >= avg else "below"
            return f"ECAT {ecat['obtained']:g}/400 is {rel} the Fall 2026 average for your group ({avg}/400) - heuristic"
    if margin is None:
        return "unknown - minimum marks not published"
    bands = [(10, "low to moderate"), (20, "moderate"), (999, "good")] if prog.get("demand") == "high" else [(5, "moderate"), (15, "good"), (999, "strong")]
    return next(label for cut, label in bands if margin < cut) + " (heuristic)"


def how_to_apply(inst: str, kb: Knowledge | None = None, on: date | None = None) -> dict:
    kb = kb or get_knowledge()
    on = on or today()
    proc = kb.processes.get(inst, {})
    inst_info = kb.institutions[inst]
    related = {inst} | ({"pmdc", "pmc"} if inst in ("jac", "szabmu") else set())
    return {"institution": inst_info["name"], "portal": proc.get("portal") or inst_info.get("admission_portal") or inst_info.get("admission_page"),
            "website_status": inst_info.get("website_status"), "working_channels": inst_info.get("working_channels"),
            "steps": proc.get("steps", []), "required_documents": proc.get("required_documents", []),
            "contacts": inst_info.get("contacts", []),
            **{k: proc[k] for k in ("age_limit", "reserved_seats", "scholarships", "fee_rules", "refund", "eligibility") if k in proc},
            "dates": [d for d in upcoming_deadlines(kb, on, include_past_days=45) if d["institution"] in related],
            "sources": proc.get("sources", [])}


def upcoming_deadlines(kb: Knowledge, on: date, include_past_days: int = 0) -> list[dict]:
    out = []
    for d in kb.dated_deadlines:
        dd = d["date"] if isinstance(d["date"], date) else date.fromisoformat(str(d["date"]))
        days = (dd - on).days
        if days >= -include_past_days:
            out.append({**d, "date": dd.isoformat(), "days_left": days})
    return sorted(out, key=lambda x: x["date"])


def test_info(test_id: str, kb: Knowledge | None = None) -> dict:
    kb = kb or get_knowledge()
    return {"id": test_id, **kb.tests[test_id]}
