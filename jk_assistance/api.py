"""FastAPI server for JK Assistance (admissions): REST API + the web portal (web/index.html).

Run:  python -m uvicorn jk_assistance.api:app --port 8010   ->  http://localhost:8010
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import advisor, assistant
from .config import DOCUMENTS_DIR, WEB_DIR, llm_enabled, today
from .knowledge import get_knowledge

app = FastAPI(title="JK Assistance - Admissions", version="0.2.0",
              description="Admission guidance for AJK students after 12 years of education: eligibility, tests, documents, fees, steps and dates.")
app.mount("/documents", StaticFiles(directory=DOCUMENTS_DIR), name="documents")


class Score(BaseModel):
    obtained: float
    total: float | None = None


class AdviseIn(BaseModel):
    group: str
    hssc: float | Score
    ssc: float | Score | None = None
    tests: dict[str, float | Score] | None = None  # mdcat, ecat, uajk_entry_test, must_seet, hec_lat
    interests: list[str] | None = None
    institutions: list[str] | None = None
    age: int | None = None
    state_subject: bool | None = None
    studied_math: bool | None = None


class ChatIn(BaseModel):
    message: str
    profile: dict[str, Any] | None = None


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health():
    kb = get_knowledge()
    return {"ok": True, "today": today().isoformat(), "llm": llm_enabled(), "programs": len(kb.programs), "tests": len(kb.tests), "chunks": len(kb.chunks)}


@app.get("/api/institutions")
def institutions():
    return list(get_knowledge().institutions.values())


@app.get("/api/programs")
def programs(institution: str | None = None, field: str | None = None):
    return [p for p in get_knowledge().programs.values() if (not institution or p["institution"] == institution) and (not field or p["field"] == field)]


@app.get("/api/tests")
def tests():
    return [{"id": k, **v} for k, v in get_knowledge().tests.items()]


@app.get("/api/tests/{test_id}")
def test(test_id: str):
    kb = get_knowledge()
    if test_id not in kb.tests:
        raise HTTPException(404, "unknown test")
    return advisor.test_info(test_id, kb)


@app.post("/api/advise")
def advise(body: AdviseIn):
    return advisor.advise(body.model_dump(exclude_none=True))


@app.get("/api/how-to-apply/{institution}")
def how_to_apply(institution: str):
    if institution not in get_knowledge().processes:
        raise HTTPException(404, "institution must be one of: uajk, must, jac")
    return advisor.how_to_apply(institution)


@app.get("/api/deadlines")
def deadlines(institution: str | None = None, include_past_days: int = 45):
    kb = get_knowledge()
    dl = advisor.upcoming_deadlines(kb, today(), include_past_days=include_past_days)
    rules = kb.rules
    if institution:
        dl = [d for d in dl if d["institution"] == institution]
        rules = [r for r in rules if r["institution"] == institution]
    return {"today": today().isoformat(), "dated": dl, "rules": rules}


@app.get("/api/search")
def search(q: str, institution: str | None = None, k: int = 8):
    return [{"score": round(s, 2), "source": c.source, "trust": c.trust, "kind": c.kind, "text": c.text[:600]}
            for s, c in get_knowledge().search(q, institution, k=k)]


@app.post("/api/chat")
def chat(body: ChatIn):
    return assistant.answer(body.message, body.profile)
