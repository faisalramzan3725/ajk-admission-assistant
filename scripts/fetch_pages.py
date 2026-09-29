"""Fetch web pages for the AJK university VA knowledge base.

Usage: python scripts/fetch_pages.py <site> <url> [<url> ...]
Saves raw/<site>/<slug>.html and raw/<site>/<slug>.txt, and prints document links found.
"""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import bs4
import requests
import urllib3

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
DOC_EXT = re.compile(r"\.(pdf|docx?|xlsx?|jpe?g|png)(\?|$)|sdm_process_download|drive\.google\.com/file", re.I)


def slug(url):
    p = urlparse(url)
    s = (p.path.strip("/") or "home") + ("_" + p.query if p.query else "")
    return re.sub(r"[^A-Za-z0-9]+", "_", s)[:90].strip("_") or "home"


def page_text(html):
    soup = bs4.BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "form"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.find(class_=re.compile("entry-content|content-area|page-content")) or soup.body or soup
    text = main.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


def fetch(site, url):
    out = ROOT / "raw" / site
    out.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers=HEADERS, timeout=60, verify=False)
    name = slug(url)
    (out / f"{name}.html").write_text(r.text, encoding="utf-8")
    txt = page_text(r.text)
    (out / f"{name}.txt").write_text(f"SOURCE: {url}\n\n{txt}", encoding="utf-8")
    soup = bs4.BeautifulSoup(r.text, "lxml")
    docs = {(a.get_text(" ", strip=True)[:80], urljoin(url, a["href"])) for a in soup.find_all("a", href=True) if DOC_EXT.search(a["href"])}
    print(f"\n##### {url} [{r.status_code}] -> {name}.txt ({len(txt)} chars)")
    for t, u in sorted(docs, key=lambda x: x[1]):
        print(f"  DOC: {t} | {u}")


if __name__ == "__main__":
    site, *urls = sys.argv[1:]
    for u in urls:
        try:
            fetch(site, u)
        except Exception as e:
            print(f"\n##### {u} FAILED: {e}")
