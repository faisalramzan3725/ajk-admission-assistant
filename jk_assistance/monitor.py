"""Proactive monitoring: compares a student's current state with the applicable rules and produces findings.

Called on every academic event (grade posted, payment, registration, application update) and on demand
(dashboard, daily sweep). Findings are then routed by decision.decide().
"""
from __future__ import annotations

from datetime import date, timedelta

from . import applications, progression
from .advisor import upcoming_deadlines
from .config import ALERT_WINDOW_DAYS, today
from .knowledge import get_knowledge

MUST_RULES = "https://must.edu.pk/?page_id=6258"


def finding(code, severity, title, detail, *, source=None, due_date=None, needs_info=None, needs_human=False, data=None):
    f = {"code": code, "severity": severity, "title": title, "detail": detail, "source": source,
         "needs_info": needs_info or [], "needs_human": needs_human, "data": data or {}}
    if due_date:
        f["due_date"] = due_date.isoformat()
        f["days_left"] = (due_date - today()).days
    return f


def scan(student: dict) -> list[dict]:
    kb = get_knowledge()
    on = today()
    out: list[dict] = []
    if student.get("type") == "applicant":
        return _scan_applicant(student, kb, on)

    missing = [k for k in ("institution", "program_type") if not student.get(k)]
    if missing:
        out.append(finding("profile.incomplete", "info", "Profile incomplete", "Some details are needed before rules can be applied.", needs_info=missing))

    # --- progression
    ev = progression.evaluate(student)
    if ev.get("rules_unavailable"):
        out.append(finding("progression.rules_unavailable", "info", "Promotion rules not available", ev["reason"] +
                           " Questions about promotion or probation will be referred to your department.", needs_human=False,
                           data={"institution": student.get("institution")}))
    else:
        out.extend(_progression_findings(student, ev))

    # --- attendance
    for a in progression.attendance_findings(student) if student.get("institution") == "must" else []:
        if a["level"] == "below_minimum":
            out.append(finding("attendance.below_minimum", "critical", f"Attendance below 75% in {a['course']}",
                               f"Your attendance is {a['attendance']}%. Under MUST rules a student below 75% (lectures and practicals separately) is dropped from the course.",
                               source=MUST_RULES, needs_human=True, data=a))
        else:
            out.append(finding("attendance.at_risk", "warning", f"Attendance close to the limit in {a['course']}",
                               f"Attendance is {a['attendance']}%; below 75% you will be dropped from the course. No leave counts as relaxation.",
                               source=MUST_RULES, data=a))

    # --- dues and challans
    out.extend(_dues_findings(student, kb, on))

    # --- re-checking window after a result with a failed course
    out.extend(_recheck_findings(student, kb, on))

    # --- maximum duration
    d = progression.duration_check(student)
    if d and d["remaining"] <= 2:
        out.append(finding("duration.near_max", "warning" if d["remaining"] > 0 else "critical", "Approaching the maximum degree duration",
                           f"Semester {d['current_semester']} of a maximum {d['max_semesters']}.", source=MUST_RULES, data=d, needs_human=d["remaining"] <= 0))

    # --- open applications
    for app in applications.list_for(student["id"]):
        out.extend(_application_findings(app))
    return out


def _progression_findings(student: dict, ev: dict) -> list[dict]:
    out = []
    state = ev["state"]
    last = ev["semesters"][-1] if ev["semesters"] else None
    if last:
        o = last["outcome"]
        if o == "pending":
            projection = _project_pending(student, last)
            sev = "warning" if projection["if_threshold_missed"] in ("relegated", "dropped") else "info"
            out.append(finding("progression.pending", sev, f"Semester {last['semester']} results pending",
                               " ".join(last["notes"]) + f" If the threshold is missed the predicted outcome is: {projection['if_threshold_missed']}"
                               + (f" (to semester {projection['relegate_to']})" if projection.get("relegate_to") else "") + ".",
                               source=MUST_RULES, data={**last, "projection": projection}))
        elif o == "probation":
            out.append(finding("progression.probation", "warning", f"On probation after semester {last['semester']}",
                               " ".join(last["notes"]) + " You may repeat failed courses in the summer semester; meeting the requirement after summer waives the probation. Failing the threshold again leads to being dropped (semester 2) or relegated (later semesters).",
                               source=MUST_RULES, data=last, needs_human=last["needs_human"]))
        elif o in ("dropped", "relegated"):
            out.append(finding(f"progression.{o}", "critical", f"{o.capitalize()} after semester {last['semester']}",
                               " ".join(last["notes"]), source=MUST_RULES, data=last, needs_human=True))
        if o not in ("probation", "dropped", "relegated") and state["on_probation"]:
            out.append(finding("progression.probation_active", "warning", f"You are on probation (probation {state['probations_used']} of the 2 allowed)",
                               "The earlier probation stands until the end of this half of the program; another semester below the promotion threshold leads to relegation "
                               "(or being dropped in semester 2). Passing the failed courses in the summer semester can waive it.",
                               source=MUST_RULES, data={"state": state}))
    normal = progression.PROGRAMS[ev["program_type"]]["normal"]
    if last and last["semester"] >= normal and last["outcome"] != "pending":
        dc = progression.degree_check(student)
        if dc["eligible"]:
            out.append(finding("degree.ready", "info", "You meet the degree requirements",
                               f"CGPA {dc['cgpa']:.2f} ({dc['cumulative_percent']}%). Next: department clearance certificate (11 offices + alumni portal for NTC), "
                               "then the Degree Form to the Controller of Examinations. Ask me for 'MUST clearance' or 'MUST degree' for the checklists.",
                               source="https://must.edu.pk/wp-content/uploads/2026/08/Degree-from-updates.pdf", data=dc))
        else:
            out.append(finding("degree.not_ready", "warning", "Degree requirements not yet met",
                               f"CGPA {dc['cgpa']} (needs 2.5 / 57.5%); outstanding failed courses: {', '.join(dc['failed_courses_outstanding']) or 'none'}.",
                               source=MUST_RULES, data=dc))
    cg = ev["cgpa"]
    if cg["gpa"] is not None and cg["gpa"] < progression.DEGREE_MIN_CGPA:
        out.append(finding("progression.cgpa_below_degree", "warning", f"CGPA {cg['gpa']:.2f} is below the 2.50 needed for the degree",
                           f"Cumulative weighted percentage {cg['weighted_percent']}%. The degree needs CGPA 2.5 (57.5%). Courses below B can be repeated to improve.",
                           source=MUST_RULES, data=cg))
    if cg.get("conflict"):
        out.append(finding("policy.conflict", "info", "Published grading rules disagree", cg["conflict"], source="https://must.edu.pk/?page_id=6252", needs_human=True))
    return out


def _project_pending(student: dict, last: dict) -> dict:
    """What-if: outcome if every pending course is failed vs. passed (limited future-state reasoning)."""
    fail = progression.what_if(student, {code: 0 for code in last["pending"]})
    ok = progression.what_if(student, {code: 60 for code in last["pending"]})
    f_last, p_last = fail["semesters"][-1], ok["semesters"][-1]
    return {"if_threshold_missed": f_last["outcome"], "relegate_to": f_last.get("relegate_to"),
            "if_all_pending_passed": p_last["outcome"], "must_pass": max(0, last["required"] - last["passed"])}


def _dues_findings(student: dict, kb, on: date) -> list[dict]:
    out = []
    uajk_rule = kb.relative_rules.get("uajk.semester_fee")
    for due in student.get("dues", []):
        if due.get("paid"):
            continue
        dd = date.fromisoformat(due["due_date"]) if due.get("due_date") else None
        # UAJK semester fee: fine windows counted from the semester start
        if student.get("institution") == "uajk" and due.get("kind") == "semester_fee" and student.get("semester_start") and due.get("semester", 1) > 1:
            start = date.fromisoformat(student["semester_start"])
            no_fine_end = start + timedelta(weeks=uajk_rule["no_fine_until_week"]) - timedelta(days=1)
            fine_end = start + timedelta(weeks=uajk_rule["fine_until_week"]) - timedelta(days=1)
            if on <= no_fine_end:
                out.append(finding("dues.semester_fee_due", "warning" if (no_fine_end - on).days <= ALERT_WINDOW_DAYS else "info",
                                   f"{due['title']}: pay Rs. {due['amount']:,} without fine", f"No fine until {no_fine_end:%d %b %Y} (end of week 3). Generate the challan at https://challan.uajk.edu.pk/.",
                                   source=uajk_rule["source"], due_date=no_fine_end, data=due))
            elif on <= fine_end:
                fined = round(due["amount"] * (1 + uajk_rule["fine_percent"] / 100))
                out.append(finding("dues.semester_fee_fine", "critical", f"{due['title']}: 10% fine now applies",
                                   f"Pay Rs. {fined:,} (Rs. {due['amount']:,} + 10%) by {fine_end:%d %b %Y} (end of week 6).",
                                   source=uajk_rule["source"], due_date=fine_end, data={**due, "amount_with_fine": fined}))
            else:
                out.append(finding("dues.semester_fee_past_window", "critical", f"{due['title']}: past the fine window",
                                   f"The published schedule ends at week 6 ({fine_end:%d %b %Y}). What happens now is not published - contact the Directorate of Finance / your department.",
                                   source=uajk_rule["source"], data=due, needs_human=True))
            continue
        if dd is None:
            out.append(finding("dues.no_due_date", "info", f"{due['title']} - due date unknown", "Enter the challan's due date so I can remind you.", needs_info=["due_date"], data=due))
            continue
        days = (dd - on).days
        if days < 0:
            out.append(finding("dues.overdue", "critical", f"{due['title']} is overdue", f"Rs. {due['amount']:,} was due on {dd:%d %b %Y}. Late fees or blocked registration may apply.",
                               due_date=dd, data=due, source=due.get("source")))
        elif days <= ALERT_WINDOW_DAYS:
            out.append(finding("dues.due_soon", "warning", f"{due['title']} due in {days} day(s)", f"Rs. {due['amount']:,} due on {dd:%d %b %Y}.", due_date=dd, data=due, source=due.get("source")))
        else:
            out.append(finding("dues.upcoming", "info", f"{due['title']} due {dd:%d %b %Y}", f"Rs. {due['amount']:,}.", due_date=dd, data=due, source=due.get("source")))

    # MUST: registration for the next semester requires promotion AND paid dues
    if student.get("institution") == "must" and student.get("next_semester_start"):
        ns = date.fromisoformat(student["next_semester_start"])
        prereg = ns - timedelta(days=2)
        unpaid_next = [d for d in student.get("dues", []) if not d.get("paid") and d.get("kind") == "semester_fee"]
        if unpaid_next and 0 <= (prereg - on).days <= ALERT_WINDOW_DAYS:
            out.append(finding("registration.dues_block", "warning", "Pay next-semester dues before pre-registration",
                               f"Pre-registration is 2 days before the semester ({prereg:%d %b %Y}) and requires the dues to be submitted; late registration is allowed only within one week after the start, with a late fee.",
                               source=MUST_RULES, due_date=prereg))
    return out


def _recheck_findings(student: dict, kb, on: date) -> list[dict]:
    out = []
    declared = student.get("result_declared_on")
    sems = sorted(student.get("semesters", []), key=lambda s: s["number"])
    if not declared or not sems:
        return out
    failed = [c["code"] for c in sems[-1].get("courses", []) if progression.course_passed(c) is False]
    rule = kb.relative_rules.get(f"{student.get('institution')}.rechecking")
    if not failed or not rule:
        return out
    due = date.fromisoformat(declared) + timedelta(days=rule["days_after_result"])
    if on <= due:
        out.append(finding("rechecking.window_open", "warning" if (due - on).days <= 7 else "info", "Re-checking window is open",
                           f"You failed {', '.join(failed)}. {rule['rule']} - apply by {due:%d %b %Y} if you believe the result is wrong.",
                           source=rule["source"], due_date=due, data={"courses": failed}))
    return out


def _application_findings(app: dict) -> list[dict]:
    out = []
    if app["status"] in ("completed", "rejected"):
        return out
    missing = [c["item"] for c in app["checklist"] if not c["done"]]
    if missing and app["status"] == "draft":
        out.append(finding("application.documents_missing", "info", f"{app['service_name']}: {len(missing)} document(s) outstanding",
                           "Still needed: " + "; ".join(missing), data={"application": app["id"]}))
    for d in applications.deadlines_for(app):
        out.append(finding("application.deadline", "critical" if d["days_left"] < 3 else "warning", f"{app['service_name']}: submission deadline",
                           f"{d['rule']} - submit by {d['due_date']}.", due_date=date.fromisoformat(d["due_date"]), data={"application": app["id"]}))
    return out


def _scan_applicant(student: dict, kb, on: date) -> list[dict]:
    out = []
    wanted = set(student.get("target_institutions") or [])
    for d in upcoming_deadlines(kb, on, audience="applicants"):
        if wanted and d["institution"] not in wanted:
            continue
        dd = date.fromisoformat(d["date"])
        sev = "warning" if d["days_left"] <= ALERT_WINDOW_DAYS else "info"
        out.append(finding("admission.deadline", sev, d["title"], d.get("action", ""), source=d["source"], due_date=dd,
                           data={"trust": d.get("trust")}))
    if not student.get("hssc_percent") or not student.get("group"):
        out.append(finding("profile.incomplete", "info", "Tell me your intermediate group and marks",
                           "I need these to check eligibility and chances.", needs_info=["group", "hssc_percent"]))
    return out
