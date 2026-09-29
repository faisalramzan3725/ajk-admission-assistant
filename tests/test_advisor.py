"""Admission engine tests. Run: python -m pytest -q"""
import pytest
import yaml

from jk_assistance import advisor, assistant, decision
from jk_assistance.config import KNOWLEDGE_DIR
from jk_assistance.knowledge import get_knowledge


def prog(result, pid):
    return next(p for p in result["programs"] if p["id"] == pid)


def check(p, criterion_start):
    return next(c for c in p["checks"] if c["criterion"].startswith(criterion_start))


# ---------------------------------------------------------------- marks parsing
@pytest.mark.parametrize("value,total,expected", [
    (86, None, 86.0), ("86%", None, 86.0), ("946/1100", None, 86.0), ({"obtained": 946, "total": 1100}, None, 86.0),
    (140, 180, 77.78), ({"obtained": 210}, 400, 52.5), (None, None, None)])
def test_to_percent(value, total, expected):
    assert advisor.to_percent(value, total) == expected


# ---------------------------------------------------------------- official test facts
def test_mdcat_and_ecat_max_and_min_marks():
    t = get_knowledge().tests
    assert t["mdcat"]["max_marks"] == 180
    assert t["mdcat"]["passing"]["mbbs"] == {"percent": 55, "marks": 99}
    assert t["mdcat"]["passing"]["bds"] == {"percent": 50, "marks": 90}
    assert t["mdcat"]["merit_formula"] == {"mdcat": 50, "hssc": 40, "ssc": 10}
    assert t["ecat"]["max_marks"] == 400
    assert t["ecat"]["passing"]["pec_engineering"]["marks"] == 132


def test_jac_website_marked_not_working_with_alternatives():
    jac = get_knowledge().institutions["jac"]
    assert "NOT WORKING" in jac["website_status"] and len(jac["working_channels"]) >= 3
    how = advisor.how_to_apply("jac")
    assert how["working_channels"] and "szabmu" in " ".join(s["detail"] for s in how["steps"]).lower()


# ---------------------------------------------------------------- eligibility checklists
def test_mbbs_eligible_with_required_vs_obtained():
    r = advisor.advise({"group": "pre_med", "hssc": "946/1100", "ssc": "1010/1100", "tests": {"mdcat": 140}, "state_subject": True, "interests": ["medicine"]})
    mbbs = prog(r, "jac.mbbs")
    assert mbbs["eligibility"] == "eligible"
    c = check(mbbs, "MDCAT")
    assert c["required"] == "≥ 55% = 99 / 180" and c["yours"] == "140 / 180 = 77.78%" and c["status"] == "pass"
    assert mbbs["merit_aggregate"] == pytest.approx(0.5 * 77.78 + 0.4 * 86 + 0.1 * 91.82, abs=0.01)


def test_mdcat_below_99_fails_mbbs_but_passes_bds():
    r = advisor.advise({"group": "pre_med", "hssc": 80, "tests": {"mdcat": 95}, "state_subject": True, "interests": ["medicine", "dentistry"]})
    assert prog(r, "jac.mbbs")["eligibility"] == "not_eligible"
    assert prog(r, "jac.bds")["eligibility"] == "eligible"


def test_medical_without_mdcat_is_pending_not_rejected():
    r = advisor.advise({"group": "pre_med", "hssc": 80, "state_subject": True, "interests": ["medicine"]})
    assert prog(r, "jac.mbbs")["eligibility"] == "eligible_after_test"


def test_hssc_below_60_blocks_mbbs():
    r = advisor.advise({"group": "pre_med", "hssc": 58, "tests": {"mdcat": 150}, "state_subject": True, "interests": ["medicine"]})
    assert prog(r, "jac.mbbs")["eligibility"] == "not_eligible"


def test_ecat_accepted_as_any_one_test_for_must_engineering():
    r = advisor.advise({"group": "pre_eng", "hssc": "880/1100", "tests": {"ecat": 210}, "interests": ["engineering"]})
    eng = prog(r, "must.engineering")
    assert eng["eligibility"] == "eligible"
    assert check(eng, "ECAT")["required"] == "≥ 33% = 132 / 400"
    assert "above the Fall 2026 average" in eng["chance"]


def test_ecat_below_132_fails_but_seet_still_open():
    r = advisor.advise({"group": "pre_eng", "hssc": 80, "tests": {"ecat": 120}, "interests": ["engineering"]})
    eng = prog(r, "must.engineering")
    assert check(eng, "ECAT")["status"] == "fail"
    assert eng["eligibility"] == "eligible_after_test"  # MUST's own SEET can still qualify the student
    r = advisor.advise({"group": "pre_eng", "hssc": 80, "tests": {"ecat": 120, "must_seet": "25%"}, "interests": ["engineering"]})
    assert prog(r, "must.engineering")["eligibility"] == "not_eligible"


def test_bare_test_number_means_marks_obtained():
    assert advisor.to_percent(95, 180) == 52.78
    assert advisor.to_percent("71%", 180) == 71.0


def test_wrong_group_and_low_marks():
    r = advisor.advise({"group": "fa", "hssc": 55, "interests": ["engineering"]})
    assert all(p["eligibility"] == "not_eligible" for p in r["programs"])


def test_math_required_for_pre_med_cs():
    r = advisor.advise({"group": "pre_med", "hssc": 80, "interests": ["computing"], "institutions": ["uajk"]})
    assert prog(r, "uajk.bs_cs_ai")["eligibility"] == "not_eligible"
    r = advisor.advise({"group": "pre_med", "hssc": 80, "interests": ["computing"], "institutions": ["uajk"], "studied_math": True})
    assert prog(r, "uajk.bs_cs_ai")["eligibility"] == "eligible_after_test"


def test_age_limit():
    r = advisor.advise({"group": "ics", "hssc": 70, "age": 25, "interests": ["computing"], "institutions": ["uajk"]})
    assert prog(r, "uajk.bs_cs_ai")["eligibility"] == "not_eligible"


def test_results_follow_students_interest_order():
    r = advisor.advise({"group": "pre_med", "hssc": 86, "tests": {"mdcat": 140}, "state_subject": True, "interests": ["mbbs or dpt"]})
    assert r["programs"][0]["field"] == "medicine"


def test_needs_info():
    assert advisor.advise({"group": "pre_eng"})["needs_info"] == ["hssc"]


def test_fields_open_when_no_interest():
    r = advisor.advise({"group": "ics", "hssc": 64})
    assert {f["field"] for f in r["fields_open_to_you"]} >= {"computing", "sciences"}


# ---------------------------------------------------------------- chat routing
@pytest.mark.parametrize("q,intent", [
    ("I did FSc pre-medical 946/1100, matric 1010/1100, MDCAT 140/180, I want MBBS or DPT", "admission_advice"),
    ("ICS 64%", "admission_advice"),
    ("MDCAT passing marks", "test_info"),
    ("ECAT total marks and passing", "test_info"),
    ("How do I apply to UAJK?", "how_to_apply"),
    ("how to apply for MBBS in AJK", "how_to_apply"),
    ("UAJK last date", "deadlines"),
    ("How do I get my transcript?", "off_topic"),
])
def test_chat_intents(q, intent):
    assert assistant.answer(q)["intent"] == intent


def test_parse_profile_marks():
    p = assistant.parse_profile("FSc pre-engineering 880/1100, matric 950/1100, ECAT 210")
    assert p["group"] == "pre_eng" and p["hssc"] == {"obtained": 880, "total": 1100}
    assert p["ssc"] == {"obtained": 950, "total": 1100} and p["tests"]["ecat"] == 210
    assert "engineering" not in (p.get("interests") or [])  # 'pre-engineering' is the group, not an interest


def test_escalation_and_off_topic():
    assert decision.route_message("I missed the deadline, can I still apply")[0] == decision.ESCALATE
    assert decision.route_message("what is my cgpa")[0] == decision.OFF_TOPIC
    assert decision.route_message("MDCAT admission eligibility")[0] is None


def test_english_word_must_is_not_institution():
    kb = get_knowledge()
    assert kb.detect_institution("which documents must I attach") is None
    assert kb.detect_institution("MUST admission") == "must"


# ---------------------------------------------------------------- data integrity
def test_yaml_values_not_split_by_commas():
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


def test_every_program_references_known_tests_and_groups():
    kb = get_knowledge()
    for p in kb.programs.values():
        assert set(p["groups"]) <= set(kb.groups), p["id"]
        for r in p.get("test_rules") or []:
            assert r["test"] in kb.tests, p["id"]
