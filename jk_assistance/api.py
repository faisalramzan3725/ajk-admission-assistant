"""FastAPI server for JK Assistance: REST API + the web portal (web/index.html).

Run:  uvicorn jk_assistance.api:app --reload --port 8000   ->  http://localhost:8000
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import advisor, applications, assistant, monitor, progression, store
from .config import DOCUMENTS_DIR, WEB_DIR, llm_enabled, today
from .decision import triage
from .knowledge import get_knowledge

app = FastAPI(title="JK Assistance", version="0.1.0",
              description="Policy-aware student-services assistant for UAJK, MUST and the AJK medical colleges.")
app.mount("/documents", StaticFiles(directory=DOCUMENTS_DIR), name="documents")


class ChatIn(BaseModel):
    message: str
    student_id: str | None = None
    profile: dict[str, Any] | None = None


class AdviseIn(BaseModel):
    group: str
    hssc_percent: float
    ssc_percent: float | None = None
    mdcat_percent: float | None = None
    interests: list[str] | None = None
    institutions: list[str] | None = None
    age: int | None = None
    state_subject: bool | None = None
    studied_math: bool | None = None


class EventIn(BaseModel):
    type: str  # grade_posted | attendance_updated | payment | due_added | result_declared
    payload: dict[str, Any]


class WhatIfIn(BaseModel):
    results: dict[str, float]


class ApplicationIn(BaseModel):
    service_id: str
    student_id: str | None = None


class ApplicationPatch(BaseModel):
    checklist_done: list[int] | None = None
    status: str | None = None
    fee_paid_on: str | None = None
    challan_no: str | None = None
    submitted_on: str | None = None


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health():
    kb = get_knowledge()
    return {"ok": True, "today": today().isoformat(), "llm": llm_enabled(), "chunks": len(kb.chunks),
            "services": len(kb.services), "programs": len(kb.programs)}


@app.get("/api/institutions")
def institutions():
    return list(get_knowledge().institutions.values())


@app.get("/api/services")
def services(institution: str | None = None):
    kb = get_knowledge()
    return [{"id": s["id"], "institution": s["institution"], "name": s["name"]} for s in kb.services.values()
            if not institution or s["institution"] == institution]


@app.get("/api/services/{service_id}")
def service(service_id: str):
    kb = get_knowledge()
    if service_id not in kb.services:
        raise HTTPException(404, "unknown service")
    return assistant._service_card(kb.services[service_id], kb, today())


@app.get("/api/programs")
def programs(institution: str | None = None):
    return [p for p in get_knowledge().programs.values() if not institution or p["institution"] == institution]


@app.post("/api/advise")
def advise(body: AdviseIn):
    return advisor.advise(body.model_dump(exclude_none=True))


@app.get("/api/deadlines")
def deadlines(institution: str | None = None, audience: str | None = None, include_past_days: int = 30):
    kb = get_knowledge()
    dl = advisor.upcoming_deadlines(kb, today(), audience=audience, include_past_days=include_past_days)
    rules = list(kb.relative_rules.values())
    if institution:
        dl = [d for d in dl if d["institution"] == institution]
        rules = [r for r in rules if r["institution"] == institution]
    return {"today": today().isoformat(), "dated": dl, "rules": rules}


@app.get("/api/search")
def search(q: str, institution: str | None = None, k: int = 8):
    return [{"score": round(s, 2), "id": c.id, "source": c.source, "trust": c.trust, "kind": c.kind, "text": c.text[:600]}
            for s, c in get_knowledge().search(q, institution, k=k)]


@app.get("/api/students")
def students():
    return [{k: s.get(k) for k in ("id", "name", "type", "institution", "program")} for s in store.load("students")]


def _student(sid: str) -> dict:
    s = store.get("students", sid)
    if not s:
        raise HTTPException(404, "unknown student")
    return s


@app.get("/api/students/{sid}")
def student(sid: str):
    return _student(sid)


@app.get("/api/students/{sid}/dashboard")
def dashboard(sid: str):
    s = _student(sid)
    out = {"student": {k: s.get(k) for k in ("id", "name", "type", "institution", "program", "program_type")},
           "today": today().isoformat(), "findings": triage(monitor.scan(s), sid),
           "applications": applications.list_for(sid)}
    if s.get("type") == "applicant":
        out["advice"] = assistant._trim_advice(advisor.advise(assistant._applicant_profile(s)))
    else:
        out["progression"] = progression.evaluate(s)
        out["dues"] = s.get("dues", [])
    return out


@app.post("/api/students/{sid}/events")
def event(sid: str, body: EventIn):
    """Apply an academic event, then re-run monitoring (event-driven alerts)."""
    s = _student(sid)
    p = body.payload
    if body.type in ("grade_posted", "attendance_updated"):
        sem = next((x for x in s["semesters"] if x["number"] == p["semester"]), None)
        if not sem:
            raise HTTPException(400, "unknown semester")
        course = next((c for c in sem["courses"] if c["code"] == p["code"]), None)
        if not course:
            raise HTTPException(400, "unknown course")
        if body.type == "grade_posted":
            course["percent"] = p["percent"]
        else:
            course["attendance"] = p["attendance"]
    elif body.type == "payment":
        due = next((d for d in s.get("dues", []) if d["id"] == p["due_id"]), None)
        if not due:
            raise HTTPException(400, "unknown due")
        due["paid"], due["paid_on"] = True, p.get("paid_on", today().isoformat())
    elif body.type == "due_added":
        s.setdefault("dues", []).append(p)
    elif body.type == "result_declared":
        s["result_declared_on"] = p.get("date", today().isoformat())
    else:
        raise HTTPException(400, "unsupported event type")
    store.upsert("students", s)
    store.append("events", {"student_id": sid, "type": body.type, "payload": p, "on": today().isoformat()})
    return {"applied": body.type, "findings": triage(monitor.scan(s), sid)}


@app.post("/api/students/{sid}/what-if")
def what_if(sid: str, body: WhatIfIn):
    return progression.what_if(_student(sid), body.results)


@app.post("/api/applications")
def create_application(body: ApplicationIn):
    try:
        return applications.create(body.service_id, body.student_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.patch("/api/applications/{app_id}")
def patch_application(app_id: str, body: ApplicationPatch):
    try:
        return applications.update(app_id, **body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "unknown application")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/applications")
def list_applications(student_id: str | None = None):
    return applications.list_for(student_id)


@app.get("/api/escalations")
def escalations(status: str | None = "open"):
    return [e for e in store.load("escalations") if not status or e["status"] == status]


@app.post("/api/escalations/{esc_id}/resolve")
def resolve(esc_id: str, note: str = ""):
    e = store.get("escalations", esc_id)
    if not e:
        raise HTTPException(404, "unknown escalation")
    e.update(status="resolved", resolution=note, resolved_on=today().isoformat())
    return store.upsert("escalations", e)


@app.post("/api/chat")
def chat(body: ChatIn):
    return assistant.answer(body.message, body.student_id, body.profile)
