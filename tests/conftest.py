"""Test environment: fixed date, no LLM calls, and an isolated copy of the demo data (never touches ./data)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["JK_TODAY"] = "2026-09-29"
os.environ["JK_DISABLE_LLM"] = "1"
os.environ["JK_DATA_DIR"] = tempfile.mkdtemp(prefix="jk-test-")
sys.path.insert(0, str(ROOT))
subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_demo.py")], check=True, env=os.environ, capture_output=True)
