"""Test environment: fixed date and no LLM calls."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["JK_TODAY"] = "2026-09-29"
os.environ["JK_DISABLE_LLM"] = "1"
sys.path.insert(0, str(ROOT))
