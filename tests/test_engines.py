"""Tests for the rule engines. Run: python -m pytest -q"""
from datetime import date

import pytest

from jk_assistance import advisor, decision, progression
from jk_assistance.knowledge import get_knowledge


def c(code, pct, credits=3, att=None, lab=None):
    return {"code": code, "credits": credits, "percent": pct, "attendance": att, "lab_percent": lab}


def student(*semesters, ptype="bs4"):
    return {"institution": "must", "program_type": ptype,
            "semesters": [{"number": i + 1, "courses": s} if isinstance(s, list) else {"number": i + 1, **s} for i, s in enumerate(semesters)]}


# ---------------------------------------------------------------- grading table
@pytest.mark.parametrize("pct,gp", [(49.9, 0.0), (50, 2.0), (55, 2.25), (60, 2.5), (63.92, 2.65), (70, 3.0), (80, 3.5), (89, 3.95), (90, 4.0), (100, 4.0)])
def test_gp_table_matches_must(pct, gp):
    assert progression.gp_from_percent(pct) == gp


def test_published_cgpa_example():
    # MUST worked example: semester I (52x4, 70x3, 54x2, 80x1, 75x3) + semester II (52x4, 50x3, 50x1) -> 59.0 -> 2.45
    s = student([c("a", 52, 4), c("b", 70), c("c", 54, 2), c("d", 80, 1), c("e", 75)],
                [c("f", 52, 4), c("g", 50), c("h", 50, 1)])
    rep = progression.gpa_report(progression.all_courses(s))
    assert rep["weighted_percent"] == 59.0 and rep["gpa"] == 2.45


def test_semester_example_and_conflict_flag():
    rep = progression.gpa_report([c("a", 52, 4), c("b", 70), c("c", 54, 2), c("d", 80, 1), c("e", 75)])
    assert rep["weighted_percent"] == 63.92 and rep["gpa"] == 2.65
    assert rep["conflict"]  # the two MUST pages disagree (2.65 vs 2.70) - must be surfaced


def test_f_grades_excluded_from_percentage():
    rep = progression.gpa_report([c("a", 80), c("b", 30)])
    assert rep["weighted_percent"] == 80


def test_lab_and_attendance_fail_course():
    assert progression.course_passed(c("a", 70, lab=40)) is False
    assert progression.course_passed(c("a", 70, att=70)) is False
    assert progression.course_passed(c("a", None, att=70)) is False  # short attendance fails even before marks
    assert progression.course_passed(c("a", None)) is None


# ---------------------------------------------------------------- promotion
def outcomes(ev):
    return [(s["semester"], s["outcome"]) for s in ev["semesters"]]


def test_required_passes_rounds_half_up():
    assert [progression.required_passes(n) for n in (4, 5, 6, 7)] == [2, 3, 3, 4]


def test_first_semester_failure_is_probation():
    ev = progression.evaluate(student([c("a", 40), c("b", 40), c("c", 60), c("d", 45)]))
    assert outcomes(ev) == [(1, "probation")] and ev["state"]["probations_used"] == 1


def test_second_failure_in_semester_two_drops():
    fail = [c("a", 40), c("b", 40), c("c", 60), c("d", 45)]
    ev = progression.evaluate(student(fail, fail))
    assert outcomes(ev) == [(1, "probation"), (2, "dropped")]
    assert ev["semesters"][-1]["needs_human"] is True


def test_summer_semester_waives_probation():
    sem1 = {"courses": [c("a", 40), c("b", 40), c("c", 60), c("d", 45)], "summer": [c("a", 60)]}
    ev = progression.evaluate(student(sem1))
    assert outcomes(ev) == [(1, "promoted")] and ev["semesters"][0]["probation_waived_by_summer"]


def test_relegation_in_semester_three_while_on_probation():
    ok, fail = [c("a", 60), c("b", 60)], [c("a", 40), c("b", 40)]
    ev = progression.evaluate(student(fail, ok, fail))
    assert outcomes(ev) == [(1, "probation"), (2, "promoted"), (3, "relegated")]
    assert ev["semesters"][-1]["relegate_to"] == 3


def test_first_probation_does_not_carry_into_second_half():
    ok, fail = [c("a", 60), c("b", 60)], [c("a", 40), c("b", 40)]
    ev = progression.evaluate(student(ok, ok, ok, fail, fail))  # probation in 4, fail in 5 -> new (second) probation
    assert outcomes(ev)[-2:] == [(4, "probation"), (5, "probation")]
    assert ev["state"]["probations_used"] == 2


def test_semester_six_failure_on_probation_relegates_to_five():
    ok, fail = [c("a", 60), c("b", 60)], [c("a", 40), c("b", 40)]
    ev = progression.evaluate(student(ok, ok, ok, ok, fail, fail))
    assert outcomes(ev)[-1] == (6, "relegated") and ev["semesters"][-1]["relegate_to"] == 5


def test_no_promotion_check_in_final_semester():
    ok, fail = [c("a", 60), c("b", 60)], [c("a", 40), c("b", 40)]
    ev = progression.evaluate(student(*([ok] * 7), fail))
    assert outcomes(ev)[-1] == (8, "no_promotion_check")


def test_pending_semester_and_what_if():
    s = student([c("a", 60), c("b", 60)], [c("a", 40), c("b", 40)], [c("x", 40), c("y", None), c("z", None), c("w", 70)])
    ev = progression.evaluate(s)
    assert outcomes(ev)[-1] == (3, "pending")
    assert progression.what_if(s, {"y": 30, "z": 30})["semesters"][-1]["outcome"] == "relegated"
    assert progression.what_if(s, {"y": 55, "z": 30})["semesters"][-1]["outcome"] == "promoted"


def test_unpublished_rules_are_not_guessed():
    ev = progression.evaluate({"institution": "uajk", "program_type": "bs4", "semesters": []})
    assert ev["rules_unavailable"] is True


# ---------------------------------------------------------------- versioned fees
def test_fee_version_selected_by_date():
    kb = get_knowledge()
    fee = next(f for f in kb.services["must.degree"]["fees"] if f["item"].startswith("Degree before convocation"))
    assert kb.fee_version(fee, date(2025, 1, 1))["amount"] == 7500
    assert kb.fee_version(fee, date(2026, 7, 27))["amount"] == 7500
    assert kb.fee_version(fee, date(2026, 7, 28))["amount"] == 9080


def test_every_service_has_sources_and_valid_forms():
    kb = get_knowledge()
    from jk_assistance.config import ROOT
    for s in kb.services.values():
        assert s.get("sources"), s["id"]
        for f in s.get("forms", []):
            if f.get("local"):
                assert (ROOT / f["local"]).exists(), f["local"]


def test_yaml_values_not_split_by_commas():
    """Unquoted commas inside YAML flow mappings silently split a value into a bogus key with a null value."""
    import yaml
    from jk_assistance.config import KNOWLEDGE_DIR

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                assert not (v is None and (")" in str(k) or " " in str(k))), f"{path}: suspicious key {k!r}"
                walk(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, x in enumerate(o):
                walk(x, f"{path}[{i}]")

    for f in KNOWLEDGE_DIR.glob("*.yaml"):
        walk(yaml.safe_load(f.read_text(encoding="utf-8")), f.name)


# ---------------------------------------------------------------- advisor
def test_advisor_pre_med_medical():
    r = advisor.advise({"group": "pre_med", "hssc_percent": 82, "ssc_percent": 88, "mdcat_percent": 71, "interests": ["medicine"]})
    mbbs = next(p for p in r["programs"] if p["id"] == "jac.mbbs")
    assert mbbs["eligibility"] == "eligible"
    assert mbbs["merit_aggregate"] == round(0.1 * 88 + 0.4 * 82 + 0.5 * 71, 2)


def test_advisor_rejects_below_minimum_and_wrong_group():
    r = advisor.advise({"group": "fa", "hssc_percent": 55, "interests": ["engineering"]})
    assert all(p["eligibility"] == "not_eligible" for p in r["programs"])


def test_advisor_ics_computing():
    r = advisor.advise({"group": "ics", "hssc_percent": 64, "interests": ["computing"]})
    ids = {p["id"]: p for p in r["programs"]}
    assert ids["must.cs_it"]["eligibility"] == "eligible"
    assert ids["uajk.bsc_se"]["eligibility"] == "eligible"  # 60% minimum


def test_advisor_needs_info():
    assert advisor.advise({"group": "pre_eng"})["needs_info"] == ["hssc_percent"]


# ---------------------------------------------------------------- decision layer
def test_sensitive_and_exception_messages_escalate():
    assert decision.route_message("I am being harassed by a classmate")[0] == decision.ESCALATE
    assert decision.route_message("can I get an extension on my fee deadline")[0] == decision.ESCALATE
    assert decision.route_message("what documents for migration")[0] is None


def test_decide_routes():
    base = {"code": "x", "title": "t", "detail": "d", "severity": "info", "needs_info": [], "needs_human": False}
    assert decision.decide({**base, "needs_human": True})["action"] == decision.ESCALATE
    assert decision.decide({**base, "needs_info": ["due_date"]})["action"] == decision.ASK_INFO
    assert decision.decide({**base, "severity": "warning", "days_left": 3})["action"] == decision.ALERT
    assert decision.decide(base)["action"] == decision.GUIDE
