"""Create synthetic (fictional) demo students and applicants in data/.

Usage: python scripts/seed_demo.py        (resets data/students.json, applications, events, escalations)
All people are fictional; dates are chosen relative to 2026-09-29 (run the app with JK_TODAY=2026-09-29 to replay exactly).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from jk_assistance import store  # noqa: E402


def c(code, title, credits, percent, attendance=None, lab=None):
    return {"code": code, "title": title, "credits": credits, "percent": percent, "attendance": attendance, "lab_percent": lab}


STUDENTS = [
    {
        "id": "S-001", "type": "student", "name": "Areeba Sultan (demo)", "institution": "must", "program": "BS Computer Science",
        "program_type": "bs4", "duration_key": "bs_bba_bsc", "admission_term": "Fall-2025",
        "result_declared_on": "2026-09-22", "next_semester_start": "2026-10-05",
        "semesters": [
            {"number": 1, "term": "Fall-2025", "courses": [
                c("CS-101", "Programming Fundamentals", 4, 71), c("MTH-101", "Calculus I", 3, 48), c("ENG-101", "English Comprehension", 3, 66),
                c("ISL-101", "Islamic Studies", 2, 74), c("PHY-101", "Applied Physics", 3, 55), c("CS-102", "ICT", 3, 80)]},
            {"number": 2, "term": "Spring-2026", "courses": [
                c("CS-201", "Object Oriented Programming", 4, 44), c("MTH-102", "Calculus II", 3, 41), c("CS-202", "Digital Logic", 3, 52),
                c("ENG-102", "Communication Skills", 3, 47), c("PAK-101", "Pakistan Studies", 2, 68), c("STA-101", "Statistics", 3, 45)]},
            {"number": 3, "term": "Fall-2026", "courses": [
                c("CS-301", "Data Structures", 4, None, attendance=78), c("CS-302", "Discrete Structures", 3, None, attendance=72),
                c("MTH-201", "Linear Algebra", 3, 58, attendance=90), c("CS-201", "Object Oriented Programming (repeat)", 4, 43, attendance=88),
                c("CS-303", "Database Systems", 3, None, attendance=85)]},
        ],
        "dues": [
            {"id": "D1", "kind": "semester_fee", "semester": 4, "title": "Semester 4 dues (Spring-2027)", "amount": 42235, "due_date": "2026-10-03", "paid": False,
             "source": "https://must.edu.pk/wp-content/uploads/2024/11/E-Prospectus_2024-25.pdf"},
            {"id": "D2", "kind": "hostel", "title": "Hostel charges", "amount": 9000, "due_date": "2026-09-20", "paid": False},
        ],
    },
    {
        "id": "S-002", "type": "student", "name": "Hamza Rathore (demo)", "institution": "must", "program": "BS Mathematics",
        "program_type": "bs4", "duration_key": "bs_bba_bsc", "admission_term": "Fall-2022",
        "semesters": [
            {"number": 1, "term": "Fall-2022", "courses": [c("M1", "Calculus I", 3, 45), c("M2", "Set Theory", 3, 42), c("M3", "English", 3, 60), c("M4", "Physics", 3, 49)],
             "summer": [c("M1", "Calculus I (summer)", 3, 62), c("M2", "Set Theory (summer)", 3, 57)]},
            {"number": 2, "term": "Spring-2023", "courses": [c("M5", "Calculus II", 3, 70), c("M6", "Algebra", 3, 66), c("M7", "Statistics", 3, 58), c("M4", "Physics (repeat)", 3, 61)]},
        ] + [{"number": n, "term": f"T{n}", "courses": [c(f"M{n}{k}", f"Course {n}.{k}", 3, 64 + k) for k in range(5)]} for n in range(3, 9)],
        "dues": [],
    },
    {
        "id": "S-003", "type": "student", "name": "Mehwish Awan (demo)", "institution": "uajk", "program": "BS English", "program_type": "bs4",
        "admission_term": "Fall-2025", "semester_start": "2026-08-31",
        "semesters": [{"number": 1, "term": "Fall-2025", "courses": [c("ENG-1", "Intro to Literature", 3, 72), c("ENG-2", "Grammar", 3, 65)]},
                      {"number": 2, "term": "Spring-2026", "courses": [c("ENG-3", "Poetry", 3, 68), c("ENG-4", "Linguistics", 3, 59)]}],
        "dues": [{"id": "D1", "kind": "semester_fee", "semester": 3, "title": "Semester 3 fee (BS English)", "amount": 57700, "paid": False,
                  "source": "https://uajk.edu.pk/wp-content/uploads/2025/09/bs-all.pdf"}],
    },
    {
        "id": "S-004", "type": "student", "name": "Dr. Usman Kiani (demo)", "institution": "uhs", "college": "pmc", "program": "MBBS (Poonch Medical College, UHS)",
        "program_type": "mbbs", "admission_term": "2020", "semesters": [], "dues": [],
    },
    {
        "id": "A-001", "type": "applicant", "name": "Zainab Mir (demo applicant)", "group": "pre_med", "hssc_percent": 82, "ssc_percent": 88,
        "mdcat_percent": 71, "state_subject": True, "age": 18, "interests": ["medicine", "health"], "target_institutions": [],
    },
    {
        "id": "A-002", "type": "applicant", "name": "Bilal Qureshi (demo applicant)", "group": "ics", "hssc_percent": 64, "age": 19,
        "interests": ["computing", "engineering"], "target_institutions": ["uajk", "must"],
    },
]

if __name__ == "__main__":
    store.save("students", STUDENTS)
    for name in ("applications", "events", "escalations"):
        store.save(name, [])
    print(f"Seeded {len(STUDENTS)} demo records into {store.DATA_DIR}")
    print(json.dumps([{"id": s["id"], "name": s["name"]} for s in STUDENTS], indent=1))
