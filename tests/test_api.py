"""End-to-end API tests against a temporary copy of the demo data (see conftest.py). Run: python -m pytest -q"""
from fastapi.testclient import TestClient

from jk_assistance.api import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health").json()
    assert r["ok"] and r["today"] == "2026-09-29" and r["services"] > 20


def test_chat_service_question():
    r = client.post("/api/chat", json={"message": "How do I get my degree from MUST?"}).json()
    assert r["intent"] == "service" and r["cards"]["service"]["id"] == "must.degree"
    assert "9,080" in r["answer"]  # 28 July 2026 fee version is in force on 2026-09-29


def test_chat_admission_advice():
    r = client.post("/api/chat", json={"message": "I did FSc pre-medical with 82%, matric 88%, MDCAT 71%, I want MBBS"}).json()
    assert r["intent"] == "admission_advice"
    assert any(p["id"] == "jac.mbbs" for p in r["cards"]["advice"]["programs"])


def test_chat_mbbs_or_dpt_spans_institutions():
    r = client.post("/api/chat", json={"message": "I did FSc pre-medical with 82%, matric 88%, MDCAT 71%, I want MBBS or DPT"}).json()
    ids = {p["id"] for p in r["cards"]["advice"]["programs"]}
    assert "jac.mbbs" in ids and "uajk.dpt" in ids


def test_chat_computing_filter_and_deadline_routing():
    r = client.post("/api/chat", json={"message": "ICS 64% which programs can I apply for in computing?"}).json()
    assert {p["field"] for p in r["cards"]["advice"]["programs"]} == {"computing"}
    r = client.post("/api/chat", json={"message": "UAJK admission last date"}).json()
    assert r["intent"] == "deadlines" and any(d["date"] == "2026-10-05" for d in r["cards"]["deadlines"])


def test_english_word_must_is_not_institution():
    from jk_assistance.knowledge import get_knowledge
    assert get_knowledge().detect_institution("which documents must I attach") is None
    assert get_knowledge().detect_institution("MUST degree fee") == "must"


def test_chat_escalates_exception_request():
    r = client.post("/api/chat", json={"message": "Can I get an extension for my fee deadline?", "student_id": "S-003"}).json()
    assert r["action"] == "ESCALATE"
    assert client.get("/api/escalations").json()


def test_chat_asks_for_institution():
    r = client.post("/api/chat", json={"message": "what is the degree fee?"}).json()
    assert r["action"] == "ASK_INFO"


def test_dashboard_flags_probation_attendance_and_fine():
    s1 = client.get("/api/students/S-001/dashboard").json()
    codes = {f["code"] for f in s1["findings"]}
    assert {"attendance.below_minimum", "dues.overdue", "progression.pending"} <= codes
    s3 = client.get("/api/students/S-003/dashboard").json()
    assert any(f["code"] == "dues.semester_fee_fine" for f in s3["findings"])


def test_payment_event_clears_alert():
    r = client.post("/api/students/S-001/events", json={"type": "payment", "payload": {"due_id": "D2"}}).json()
    assert not any(f["code"] == "dues.overdue" for f in r["findings"])


def test_grade_event_updates_progression():
    r = client.post("/api/students/S-001/events", json={"type": "grade_posted", "payload": {"semester": 3, "code": "CS-301", "percent": 61}}).json()
    assert r["applied"] == "grade_posted"


def test_application_lifecycle():
    a = client.post("/api/applications", json={"service_id": "uajk.migration", "student_id": "S-003"}).json()
    assert a["status"] == "draft" and a["checklist"]
    a = client.patch(f"/api/applications/{a['id']}", json={"fee_paid_on": "2026-09-20"}).json()
    assert a["status"] == "fee_paid"
    dash = client.get("/api/students/S-003/dashboard").json()
    dl = [f for f in dash["findings"] if f["code"] == "application.deadline"]
    assert dl and dl[0]["due_date"] == "2026-10-05"  # 15 days after fee payment


def test_deadlines_and_search():
    d = client.get("/api/deadlines?institution=uajk").json()
    assert any(x["date"] == "2026-10-05" for x in d["dated"])
    hits = client.get("/api/search", params={"q": "migration certificate fee"}).json()
    assert hits
