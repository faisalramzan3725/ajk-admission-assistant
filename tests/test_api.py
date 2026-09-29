"""End-to-end API tests. Run: python -m pytest -q"""
from fastapi.testclient import TestClient

from jk_assistance.api import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health").json()
    assert r["ok"] and r["today"] == "2026-09-29" and r["programs"] >= 38


def test_advise_with_obtained_and_total():
    body = {"group": "pre_med", "hssc": {"obtained": 946, "total": 1100}, "ssc": {"obtained": 1010, "total": 1100},
            "tests": {"mdcat": {"obtained": 140, "total": 180}}, "state_subject": True, "interests": ["medicine"]}
    r = client.post("/api/advise", json=body).json()
    mbbs = next(p for p in r["programs"] if p["id"] == "jac.mbbs")
    assert mbbs["eligibility"] == "eligible" and mbbs["merit_aggregate"] > 80
    assert "jac" in r["how_to_apply"]


def test_tests_endpoint():
    t = {x["id"]: x for x in client.get("/api/tests").json()}
    assert t["mdcat"]["max_marks"] == 180 and t["ecat"]["max_marks"] == 400
    assert client.get("/api/tests/nope").status_code == 404


def test_how_to_apply():
    h = client.get("/api/how-to-apply/uajk").json()
    assert h["portal"] == "https://admissions.uajk.edu.pk/" and len(h["steps"]) >= 6
    assert any(d["date"] == "2026-10-05" for d in h["dates"])
    assert client.get("/api/how-to-apply/xyz").status_code == 404


def test_deadlines_are_clickable():
    d = client.get("/api/deadlines").json()
    assert any(x["id"] == "mdcat2026.test" for x in d["dated"])
    for x in d["dated"]:
        assert x["link"].startswith(("http", "/documents/")) and x["source_url"].startswith(("http", "/documents/")), x["id"]
        if x["source_url"].startswith("/documents/"):
            assert client.get(x["source_url"]).status_code == 200  # local copy is actually served
    assert "jac.ajk.gov.pk" not in " ".join(x["link"] for x in d["dated"])  # never send students to the dead JAC site
    merit3 = next(x for x in d["dated"] if x["id"] == "must.fall2026.merit3")
    assert merit3["link"] == "https://admission.must.edu.pk/meritlist.php"


def test_chat_deadlines_have_markdown_links():
    r = client.post("/api/chat", json={"message": "UAJK last date"}).json()
    assert "](https://admissions.uajk.edu.pk/)" in r["answer"]


def test_chat():
    r = client.post("/api/chat", json={"message": "MDCAT passing marks"}).json()
    assert r["intent"] == "test_info" and "99 / 180" in r["answer"]
    r = client.post("/api/chat", json={"message": "Can I get an extension after the last date?"}).json()
    assert r["action"] == "ESCALATE"


def test_removed_dashboard_endpoints_are_gone():
    assert client.get("/api/students").status_code == 404
