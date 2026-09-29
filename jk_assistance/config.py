"""Paths and runtime settings for JK Assistance."""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
RAW_DIR = ROOT / "raw"
DOCUMENTS_DIR = ROOT / "documents"
DATA_DIR = Path(os.environ.get("JK_DATA_DIR", ROOT / "data"))
WEB_DIR = ROOT / "web"

MODEL = os.environ.get("JK_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("JK_EFFORT", "medium")

# Alert when a deadline is this many days away (or less).
ALERT_WINDOW_DAYS = int(os.environ.get("JK_ALERT_WINDOW_DAYS", "14"))


def today() -> date:
    """The assistant's notion of 'today'. Set JK_TODAY=YYYY-MM-DD to replay a scenario."""
    override = os.environ.get("JK_TODAY")
    return date.fromisoformat(override) if override else date.today()


def llm_enabled() -> bool:
    """True when some Anthropic credential is configured; otherwise answers are composed without the LLM."""
    if os.environ.get("JK_DISABLE_LLM") == "1":
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
