"""Academic progression engine (semester promotion, probation, relegation, GPA/CGPA, degree eligibility).

Implements MUST's published semester regulations (knowledge/progression_rules.yaml, rule set must.semester.v2017).
For institutions whose rules are not published (UAJK) or not ingested (UHS MBBS), it returns an explicit
`rules_unavailable` result so the decision layer escalates instead of guessing.

Student record shape (see data/students.json):
  {"institution": "must", "program_type": "bs4", "semesters": [
      {"number": 1, "term": "Fall-2025",
       "courses": [{"code": "CS-101", "title": "...", "credits": 3, "percent": 72, "lab_percent": null, "attendance": 90}],
       "summer": [{"code": "...", "credits": 3, "percent": 61}]}   # optional summer re-attempts of this semester's courses
  ]}
"""
from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field

RULE_SET = "must.semester.v2017"
PASS_PERCENT = 50
MIN_ATTENDANCE = 75
ATTENDANCE_WARNING = 80
DEGREE_MIN_CGPA = 2.5
DEGREE_MIN_PERCENT = 57.5

# program_type -> parameters from the regulations
PROGRAMS = {
    "bs4": {"promotion_last": 7, "first_half": (1, 4), "second_half": (5, 8), "normal": 8, "max_probations": 2},
    "bs5": {"promotion_last": 8, "first_half": (1, 4), "second_half": (5, 8), "normal": 10, "max_probations": 2},
    "bs3": {"promotion_last": 5, "first_half": (1, 4), "second_half": (5, 6), "normal": 6, "max_probations": 2},
    "master2": {"promotion_last": 3, "first_half": (1, 3), "second_half": None, "normal": 4, "max_probations": 1},
}
MAX_SEMESTERS = {"bsc_engineering": 14, "bsc_technology": 10, "pharm_d": 14, "bs_bba_bsc": 12, "ba_llb": 14, "master_2yr": 6}

LETTERS = [(90, "A+"), (85, "A"), (80, "A-"), (75, "B+"), (70, "B"), (65, "B-"), (60, "C+"), (55, "C"), (50, "C-")]


# ---------------------------------------------------------------------------- grading
def course_passed(c: dict) -> bool | None:
    """None = result not declared yet."""
    if c.get("attendance") is not None and c["attendance"] < MIN_ATTENDANCE:
        return False  # dropped from the course for short attendance, whatever the marks
    if c.get("percent") is None:
        return None
    if c["percent"] < PASS_PERCENT:
        return False
    if c.get("lab_percent") is not None and c["lab_percent"] < PASS_PERCENT:
        return False  # theory and lab must be passed separately
    return True


def course_mark(c: dict) -> int:
    """A fraction of a mark counts as 1 (64.5 -> 65, per rule 6)."""
    return int(math.floor(c["percent"] + 0.5))


def gp_from_percent(p: float) -> float:
    """MUST GP table: <50 -> 0; 50 -> 2.00, +0.05 per whole percent; >=90 -> 4.00. No rounding of the average (truncate)."""
    if p < PASS_PERCENT:
        return 0.0
    if p >= 90:
        return 4.0
    return round(2.0 + 0.05 * (math.floor(p) - 50), 2)


def letter_grade(p: float) -> str:
    for cut, letter in LETTERS:
        if p >= cut:
            return letter
    return "F"


def weighted_percent(courses: list[dict]) -> float | None:
    """Weighted average % over PASSED courses only (F grades are excluded from the percentage, rule 5)."""
    passed = [c for c in courses if course_passed(c)]
    credits = sum(c["credits"] for c in passed)
    if not credits:
        return None
    return sum(course_mark(c) * c["credits"] for c in passed) / credits


def gpa_report(courses: list[dict]) -> dict:
    wp = weighted_percent(courses)
    if wp is None:
        return {"weighted_percent": None, "gpa": None, "letter": None, "conflict": None}
    conflict = None
    if wp - math.floor(wp) >= 0.5 and 50 <= wp < 90:
        conflict = (f"Weighted average {wp:.2f}: MUST's Grading System page implies GP {gp_from_percent(wp):.2f} (no rounding) "
                    f"but its Semester Rules example would give {gp_from_percent(math.floor(wp) + 1):.2f}. Confirm with the Controller of Examinations.")
    return {"weighted_percent": round(wp, 2), "gpa": gp_from_percent(wp), "letter": letter_grade(wp), "conflict": conflict}


def all_courses(student: dict) -> list[dict]:
    """Latest attempt of every course across semesters and summers (a repeat replaces the earlier attempt)."""
    latest: dict[str, dict] = {}
    for sem in sorted(student.get("semesters", []), key=lambda s: s["number"]):
        for c in sem.get("courses", []) + sem.get("summer", []):
            if c.get("percent") is not None:
                latest[c["code"]] = c
    return list(latest.values())


# ---------------------------------------------------------------------------- promotion
@dataclass
class SemesterOutcome:
    semester: int
    opted: int
    passed: int
    required: int
    pending: list[str]
    outcome: str  # promoted | probation | dropped | relegated | pending | no_promotion_check
    relegate_to: int | None = None
    probation_waived_by_summer: bool = False
    notes: list[str] = field(default_factory=list)
    needs_human: bool = False


@dataclass
class ProgressionState:
    on_probation: bool = False
    probations_used: int = 0
    relegation_used: bool = False
    readmission_needed: bool = False
    status: str = "active"  # active | probation | dropped | relegated
    current_semester: int = 1


def required_passes(opted: int) -> int:
    """Half the opted courses; a fractional half is rounded to the nearest whole course (x.5 rounds up)."""
    return int(math.floor(opted / 2 + 0.5))


def evaluate(student: dict) -> dict:
    """Replay every semester in order and return the progression state plus per-semester outcomes."""
    if student.get("institution") != "must":
        return {"rules_unavailable": True, "rule_set": None,
                "reason": {"uajk": "UAJK has not published its semester promotion/probation rules online.",
                           "uhs": "MBBS/BDS promotion follows UHS professional-exam regulations, which are not ingested."}.get(
                               student.get("institution"), "No progression rules are loaded for this institution.")}
    ptype = student.get("program_type", "bs4")
    if ptype not in PROGRAMS:
        return {"rules_unavailable": True, "rule_set": RULE_SET, "reason": f"Program type '{ptype}' is not modelled (supported: {', '.join(PROGRAMS)})."}
    prog = PROGRAMS[ptype]
    state = ProgressionState()
    outcomes: list[SemesterOutcome] = []

    for sem in sorted(student.get("semesters", []), key=lambda s: s["number"]):
        n = sem["number"]
        state.current_semester = n
        if prog["second_half"] and n == prog["second_half"][0]:
            if state.on_probation:
                outcomes_note = "First probation does not carry into the second half of the program."
            else:
                outcomes_note = None
            state.on_probation = False
        else:
            outcomes_note = None

        courses = sem.get("courses", [])
        results = [course_passed(c) for c in courses]
        pending = [c["code"] for c, r in zip(courses, results) if r is None]
        passed = sum(1 for r in results if r)
        opted = len(courses)
        req = required_passes(opted)
        o = SemesterOutcome(n, opted, passed, req, pending, "promoted")
        if outcomes_note:
            o.notes.append(outcomes_note)

        if n > prog["promotion_last"]:
            o.outcome = "no_promotion_check"
            o.notes.append(f"No promotion check after semester {prog['promotion_last']}; failed courses are re-registered in later semesters.")
            outcomes.append(o)
            continue
        if pending:
            o.outcome = "pending"
            need = max(0, req - passed)
            o.notes.append(f"{need} more of the {len(pending)} pending course(s) must be passed to meet the promotion threshold ({req} of {opted}).")
            outcomes.append(o)
            break

        met = passed >= req
        if not met and sem.get("summer"):
            summer_passed = {c["code"] for c in sem["summer"] if course_passed(c)}
            failed_codes = {c["code"] for c, r in zip(courses, results) if not r}
            recovered = len(summer_passed & failed_codes)
            if passed + recovered >= req:
                met = True
                o.passed = passed + recovered
                o.probation_waived_by_summer = True
                o.notes.append(f"Summer semester recovered {recovered} course(s); the promotion requirement is met, so probation is waived.")

        if met:
            o.outcome = "promoted"
            if state.on_probation:
                o.notes.append("Promoted; the earlier probation still stands until the end of this half of the program.")
        else:
            _apply_failure(n, prog, state, o)
        outcomes.append(o)
        if o.outcome == "dropped":
            break

    return {
        "rules_unavailable": False,
        "rule_set": RULE_SET,
        "program_type": ptype,
        "state": asdict(state),
        "semesters": [asdict(o) for o in outcomes],
        "cgpa": gpa_report(all_courses(student)),
        "semester_gpa": {s["number"]: gpa_report(s.get("courses", [])) for s in student.get("semesters", [])},
    }


def _apply_failure(n: int, prog: dict, state: ProgressionState, o: SemesterOutcome) -> None:
    first_lo, first_hi = prog["first_half"]
    in_first = first_lo <= n <= first_hi
    if not state.on_probation:
        if state.probations_used >= prog["max_probations"]:
            o.outcome = "probation"
            o.needs_human = True
            o.notes.append(f"Below the threshold with all {prog['max_probations']} allowed probation(s) already used - the regulations do not say what happens next; refer to the department.")
            return
        state.on_probation = True
        state.probations_used += 1
        state.status = "probation"
        o.outcome = "probation"
        o.notes.append(("First" if state.probations_used == 1 else "Second") + f" probation: passed {o.passed} of {o.opted}, needed {o.required}.")
        return
    # already on probation
    if in_first and n <= 2:
        o.outcome = "dropped"
        state.status = "dropped"
        state.readmission_needed = True
        o.needs_human = True
        o.notes.append("Dropped - re-admission to semester 1 of the same discipline is allowed once, or a fresh admission on merit.")
        return
    relegate_to = _relegation_target(n, prog, in_first)
    if state.relegation_used:
        o.outcome = "relegated"
        o.relegate_to = relegate_to
        o.needs_human = True
        o.notes.append("Relegation is granted only once and has already been used - the case needs a decision by the department.")
        return
    state.relegation_used = True
    state.on_probation = False
    state.status = "relegated"
    o.outcome = "relegated"
    o.relegate_to = relegate_to
    o.needs_human = True
    o.notes.append(f"Relegated to semester {relegate_to} (failed the threshold while on probation).")


def _relegation_target(n: int, prog: dict, in_first: bool) -> int:
    """Semester 3/4 -> 3; semester 6 -> 5; semester 7 or 8 -> 7 (master programs: semester 3 -> 3)."""
    if in_first:
        return 3
    second_start = prog["second_half"][0]
    return second_start if n == second_start + 1 else max(n if n < 7 else 7, second_start)


# ---------------------------------------------------------------------------- what-if + checks
def what_if(student: dict, hypothetical: dict[str, float]) -> dict:
    """Re-run the evaluation with hypothetical percentages for pending (or any) courses: {'CS-201': 45, ...}."""
    s = copy.deepcopy(student)
    for sem in s.get("semesters", []):
        for c in sem.get("courses", []):
            if c["code"] in hypothetical:
                c["percent"] = hypothetical[c["code"]]
    return evaluate(s)


def attendance_findings(student: dict) -> list[dict]:
    out = []
    semesters = sorted(student.get("semesters", []), key=lambda s: s["number"])
    if not semesters:
        return out
    for c in semesters[-1].get("courses", []):
        a = c.get("attendance")
        if a is None:
            continue
        if a < MIN_ATTENDANCE:
            out.append({"course": c["code"], "attendance": a, "level": "below_minimum"})
        elif a < ATTENDANCE_WARNING:
            out.append({"course": c["code"], "attendance": a, "level": "at_risk"})
    return out


def degree_check(student: dict) -> dict:
    report = gpa_report(all_courses(student))
    failed_outstanding = sorted({c["code"] for c in _latest_attempts(student) if course_passed(c) is False})
    ok = (report["gpa"] or 0) >= DEGREE_MIN_CGPA and (report["weighted_percent"] or 0) >= DEGREE_MIN_PERCENT and not failed_outstanding
    return {"eligible": ok, "cgpa": report["gpa"], "cumulative_percent": report["weighted_percent"],
            "required_cgpa": DEGREE_MIN_CGPA, "required_percent": DEGREE_MIN_PERCENT, "failed_courses_outstanding": failed_outstanding}


def _latest_attempts(student: dict) -> list[dict]:
    latest: dict[str, dict] = {}
    for sem in sorted(student.get("semesters", []), key=lambda s: s["number"]):
        for c in sem.get("courses", []) + sem.get("summer", []):
            if c.get("percent") is not None:
                latest[c["code"]] = c
    return list(latest.values())


def duration_check(student: dict) -> dict | None:
    key = student.get("duration_key")
    if key not in MAX_SEMESTERS:
        return None
    current = max((s["number"] for s in student.get("semesters", [])), default=0)
    return {"current_semester": current, "max_semesters": MAX_SEMESTERS[key], "remaining": MAX_SEMESTERS[key] - current}
