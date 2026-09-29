"""Application processing: turns a service (degree, transcript, migration, clearance...) into a tracked case
with a document checklist, the fee that applies on the application date, forms, steps and deadlines."""
from __future__ import annotations

from datetime import date, timedelta

from . import store
from .config import today
from .knowledge import get_knowledge

STATUSES = ["draft", "documents_ready", "fee_paid", "submitted", "in_process", "completed", "rejected"]


def create(service_id: str, student_id: str | None = None, fee_items: list[str] | None = None) -> dict:
    kb = get_knowledge()
    if service_id not in kb.services:
        raise KeyError(f"Unknown service '{service_id}'")
    s = kb.services[service_id]
    on = today()
    fees = kb.service_fees(service_id, on)
    if fee_items:
        fees = [f for f in fees if f["item"] in fee_items] or fees
    app = {
        "id": store.next_id("applications", "APP"),
        "student_id": student_id,
        "service_id": service_id,
        "institution": s["institution"],
        "service_name": s["name"],
        "office": s.get("office"),
        "portal": s.get("portal"),
        "created_on": on.isoformat(),
        "status": "draft",
        "checklist": [{"item": d, "done": False} for d in s.get("required_documents", [])],
        "forms": s.get("forms", []),
        "steps": s.get("steps", []),
        "fees": fees,
        "fee_paid_on": None,
        "challan_no": None,
        "submitted_on": None,
        "history": [{"on": on.isoformat(), "status": "draft"}],
        "sources": s.get("sources", []),
    }
    return store.upsert("applications", app)


def update(app_id: str, *, checklist_done: list[int] | None = None, status: str | None = None,
           fee_paid_on: str | None = None, challan_no: str | None = None, submitted_on: str | None = None) -> dict:
    app = store.get("applications", app_id)
    if not app:
        raise KeyError(app_id)
    for i in checklist_done or []:
        if 0 <= i < len(app["checklist"]):
            app["checklist"][i]["done"] = True
    if fee_paid_on:
        app["fee_paid_on"] = fee_paid_on
    if challan_no:
        app["challan_no"] = challan_no
    if submitted_on:
        app["submitted_on"] = submitted_on
    if status:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        app["status"] = status
    elif app["status"] == "draft" and app["checklist"] and all(c["done"] for c in app["checklist"]):
        app["status"] = "documents_ready"
    if app["fee_paid_on"] and app["status"] in ("draft", "documents_ready"):
        app["status"] = "fee_paid"
    app["history"].append({"on": today().isoformat(), "status": app["status"]})
    return store.upsert("applications", app)


def deadlines_for(app: dict) -> list[dict]:
    """Relative deadlines of the service, anchored on the fee payment date (e.g. migration: submit within 15 days)."""
    kb = get_knowledge()
    out = []
    for rule in kb.services[app["service_id"]].get("deadlines", []):
        if "days_after_payment" in rule and app.get("fee_paid_on") and not app.get("submitted_on"):
            due = date.fromisoformat(app["fee_paid_on"]) + timedelta(days=rule["days_after_payment"])
            out.append({"rule": rule["rule"], "due_date": due.isoformat(), "days_left": (due - today()).days})
    return out


def list_for(student_id: str | None = None) -> list[dict]:
    return [a for a in store.load("applications") if student_id is None or a.get("student_id") == student_id]
