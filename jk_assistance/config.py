"""Paths and runtime settings for JK Assistance."""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
RAW_DIR = ROOT / "raw"
DOCUMENTS_DIR = ROOT / "documents"
WEB_DIR = ROOT / "web"

MODEL = os.environ.get("JK_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("JK_EFFORT", "medium")


def today() -> date:
    """The assistant's notion of 'today'. Set JK_TODAY=YYYY-MM-DD to replay a scenario."""
    override = os.environ.get("JK_TODAY")
    return date.fromisoformat(override) if override else date.today()


def llm_enabled() -> bool:
    """True when an Anthropic credential is configured; otherwise answers are rendered from the rule engines."""
    if os.environ.get("JK_DISABLE_LLM") == "1":
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
