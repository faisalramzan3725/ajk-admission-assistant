"""Claude answer composer. The deterministic engines decide WHAT is true; Claude only phrases it,
grounded in numbered evidence, and must say when the evidence doesn't cover the question."""
from __future__ import annotations

import json
import logging

import anthropic

from .config import EFFORT, MODEL

log = logging.getLogger(__name__)

SYSTEM = """You are JK Assistance, an ADMISSION assistant for students in Azad Jammu & Kashmir who have finished 12 years of
education and don't know where to go or how to apply. You cover UAJK (Muzaffarabad), MUST (Mirpur), the AJK public medical
colleges (AJKMC, MBBSMC, Poonch Medical College) and SZABMU federal medical colleges with AJK-quota seats, plus the entry tests
(MDCAT out of 180, ECAT out of 400, UAJK entry test, MUST SEET, HEC LAT).

Rules:
- Use ONLY the numbered evidence and the STRUCTURED RESULT you are given. Cite evidence inline as [1], [2].
- The STRUCTURED RESULT comes from rule engines and is authoritative for eligibility checks (required vs obtained marks),
  merit aggregates, fees, dates and the recommended action. Never contradict it. Show required and obtained marks as "x / max".
- Lead with what the student should do next (which programs, which test, which steps, which deadline).
- The JAC website (jac.ajk.gov.pk) is not working: never send students there; use the working channels in the result.
- Quote every fee with its session year.
- Mark facts from sources with trust=secondary as "reported by a third-party site - verify with the office".
- If the evidence does not answer the question, say so plainly and name the office/phone/email to contact. Never invent fees,
  dates, phone numbers, merit cut-offs or rules.
- Chance estimates are heuristics; say so.
- If ACTION is ESCALATE, explain briefly why the admission office must decide and who to contact.
- Only answer admission questions; for anything else say JK Assistance covers admissions only.
- Reply in the user's language (English or Urdu/Roman Urdu). Be concise: short paragraphs and checklists."""


def compose(question: str, evidence: list[dict], structured: dict, action: str) -> str | None:
    """Return Claude's answer, or None if the call fails (the caller then uses the deterministic answer)."""
    ev_text = "\n\n".join(f"[{i + 1}] (source: {e['source']}; trust: {e['trust']})\n{e['text'][:2500]}" for i, e in enumerate(evidence))
    user = (f"QUESTION:\n{question}\n\nACTION: {action}\n\nSTRUCTURED RESULT (JSON):\n{json.dumps(structured, ensure_ascii=False, default=str)[:12000]}"
            f"\n\nEVIDENCE:\n{ev_text}")
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError as e:
        log.warning("Claude rate limited: %s", e)
        return None
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s: %s", e.status_code, e.message)
        return None
    except anthropic.APIConnectionError as e:
        log.warning("Claude connection error: %s", e)
        return None
    if resp.stop_reason == "refusal":
        log.warning("Claude declined: %s", getattr(resp, "stop_details", None))
        return None
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text or None
