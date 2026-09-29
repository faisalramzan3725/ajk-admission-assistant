"""Update-agent tests (offline: detectors, source list, report writer). Run: python -m pytest -q"""
import importlib.util
from pathlib import Path

import yaml

from jk_assistance.sources import document_links, page_text, slug

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("update_agent", ROOT / "scripts" / "update_agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def test_sources_list_is_valid():
    src = yaml.safe_load((ROOT / "knowledge" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    ids = [s["id"] for s in src]
    assert len(ids) == len(set(ids))
    allowed = {"dates", "fees", "rules", "links", "status"}
    for s in src:
        assert s["url"].startswith("http") and set(s["watch"]) <= allowed, s["id"]
    assert "jac.portal" in ids  # the agent tells us when the JAC site comes back


def test_slug_matches_existing_raw_files():
    assert slug("https://uajk.edu.pk/admission-procedure/") == "admission_procedure"
    assert (ROOT / "raw" / "uajk" / "admission_procedure.txt").exists()


def test_date_detector():
    text = "Last date extended to 05 October 2026. Merit list on September 18th, 2026; test 20-09-2026. " \
           "UAJK styled: 05 October 𝟐𝟎𝟐𝟔"
    found = agent.DATE_RE.findall(text)
    assert "05 October 2026" in found and any("September 18th, 2026" in f for f in found) and "20-09-2026" in found
    assert any("𝟐𝟎𝟐𝟔" in f for f in found)


def test_fee_and_rule_detectors():
    assert agent.FEE_RE.findall("Challan of Rs. 3,000 and PKR 1,000 per program") == ["Rs. 3,000", "PKR 1,000"]
    assert agent.RULE_RE.findall("Minimum 60% marks in F.Sc (Pre-Medical)")


def test_page_helpers():
    html = '<html><body><nav>menu</nav><main><h1>Admissions</h1><a href="/ad.pdf">Advertisement</a></main></body></html>'
    assert "Admissions" in page_text(html) and "menu" not in page_text(html)
    assert document_links(html, "https://x.edu.pk/p/") == [("Advertisement", "https://x.edu.pk/ad.pdf")]


def test_report_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "REPORTS", tmp_path)
    r = {"run_at": "t", "today": "2026-09-29", "sources": [{"id": "a", "url": "u", "ok": True, "status": 200, "error": None}],
         "changes": [{"id": "a", "url": "u", "added_lines": 1, "dates": ["05 October 2026"], "fees": [], "rules": [], "admission_lines": [], "sample": []}],
         "status_changes": [], "new_documents": [], "link_problems": [], "calendar_gaps": ["jac"], "proposals": [], "changed": True}
    agent.write_report(r)
    md = (tmp_path / "update_report.md").read_text(encoding="utf-8")
    assert "05 October 2026" in md and "Calendar needs the next cycle" in md
