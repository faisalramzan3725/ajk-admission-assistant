"""Decision layer for admission questions.

  GUIDE     - rule-backed admission guidance
  ASK_INFO  - more details are needed (group, marks, institution)
  ALERT     - an admission date is close or has just passed
  ESCALATE  - a person at the admission office must decide (exceptions, appeals, sensitive situations)
  OFF_TOPIC - not an admission question (JK Assistance is admission-only)
"""
from __future__ import annotations

import re

GUIDE, ASK_INFO, ALERT, ESCALATE, OFF_TOPIC = "GUIDE", "ASK_INFO", "ALERT", "ESCALATE", "OFF_TOPIC"

SENSITIVE = re.compile(r"harass|abuse|suicid|self[- ]harm|depress|threat|bully|discriminat|fake (certificate|degree|document)|forg", re.I)
EXCEPTION = re.compile(r"exception|special case|waive|relax(ation)? for me|condon|extension|extend (the )?deadline|appeal|grace marks|"
                       r"after (the )?(last date|deadline)|missed the deadline|late application", re.I)
NON_ADMISSION = re.compile(r"\b(degree (issu|verif|form)|transcript|dmc|migration certificate|clearance|probation|promot|relegat|cgpa|gpa|"
                           r"semester result|re-?checking|convocation|bonafide|hostel fee|attendance)\b", re.I)


def route_message(text: str) -> tuple[str | None, str | None]:
    if SENSITIVE.search(text):
        return ESCALATE, "This involves a sensitive or personal situation - please contact the institution's Directorate of Students' Affairs directly."
    if EXCEPTION.search(text):
        return ESCALATE, "Exceptions, late applications, appeals and relaxations are decided by the admission committee, not by published rules."
    if NON_ADMISSION.search(text) and not re.search(r"admission|apply|eligib|entry test|mdcat|ecat|merit", text, re.I):
        return OFF_TOPIC, "JK Assistance helps with admissions only (choosing a program, eligibility, tests, documents, fees and applying)."
    return None, None
