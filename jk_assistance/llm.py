"""Claude answer composer. The deterministic engines decide WHAT is true; Claude only phrases it,
grounded in numbered evidence, and must say when the evidence doesn't cover the question."""
from __future__ import annotations

import json
import logging

import anthropic

from .config import EFFORT, MODEL

log = logging.getLogger(__name__)

SYSTEM = """You are JK Assistance, a student-services assistant for universities and medical colleges in Azad Jammu & Kashmir
(UAJK Muzaffarabad, MUST Mirpur, the AJK public medical colleges admitted through JAC, and UHS Lahore for MBBS/BDS degrees).
You help applicants who finished 12 years of education choose programs and apply, and help enrolled students with documents,
fees and challans, deadlines, degrees, transcripts, verification, migration, clearance and semester promotion.

Rules:
- Use ONLY the numbered evidence and the STRUCTURED RESULT you are given. Cite evidence inline as [1], [2].
- The STRUCTURED RESULT comes from rule engines and is authoritative for eligibility, fees on the given date, deadlines,
  promotion/probation outcomes and the recommended action. Never contradict it.
- Quote every fee with the date it took effect (or the date it was fetched). If two fee versions exist, give the current one and mention the older.
- Mark facts from sources with trust=secondary as "reported by a third-party site - verify with the office".
- If the evidence does not answer the question, say so plainly and name the office/phone/email to contact. Never invent fees,
  dates, phone numbers, merit cut-offs or rules.
- Chance estimates are heuristics; say so.
- If ACTION is ESCALATE, explain briefly why a human official must decide and who to contact.
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
