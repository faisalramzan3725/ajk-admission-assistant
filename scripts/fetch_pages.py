"""Fetch web pages into raw/<site>/ (HTML + clean text) and list the document links found.

Usage: python scripts/fetch_pages.py <site> <url> [<url> ...]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from jk_assistance.sources import document_links, fetch, page_text, slug  # noqa: E402


def save(site: str, url: str) -> None:
    out = ROOT / "raw" / site
    out.mkdir(parents=True, exist_ok=True)
    res = fetch(url, timeout=60)
    if not res["ok"]:
        print(f"\n##### {url} FAILED: {res['error']}")
        return
    name = slug(url)
    (out / f"{name}.html").write_text(res["html"], encoding="utf-8")
    txt = page_text(res["html"])
    (out / f"{name}.txt").write_text(f"SOURCE: {url}\n\n{txt}", encoding="utf-8")
    print(f"\n##### {url} [{res['status']}] -> {name}.txt ({len(txt)} chars)")
    for title, link in document_links(res["html"], url):
        print(f"  DOC: {title} | {link}")


if __name__ == "__main__":
    site, *urls = sys.argv[1:]
    for u in urls:
        save(site, u)
