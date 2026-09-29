"""Fetching helpers shared by scripts/fetch_pages.py and the update agent."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import bs4
import requests
import urllib3

urllib3.disable_warnings()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"}
DOC_EXT = re.compile(r"\.(pdf|docx?|xlsx?|jpe?g|png)(\?|$)|sdm_process_download|drive\.google\.com/file", re.I)


def slug(url: str) -> str:
    """Stable file name for a URL (same scheme the collected raw/ files use)."""
    p = urlparse(url)
    s = (p.path.strip("/") or "home") + ("_" + p.query if p.query else "")
    return re.sub(r"[^A-Za-z0-9]+", "_", s)[:90].strip("_") or "home"


def page_text(html: str) -> str:
    soup = bs4.BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "form"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.find(class_=re.compile("entry-content|content-area|page-content")) or soup.body or soup
    return re.sub(r"\n{3,}", "\n\n", main.get_text("\n", strip=True))


def document_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = bs4.BeautifulSoup(html, "lxml")
    return sorted({(a.get_text(" ", strip=True)[:100], urljoin(base_url, a["href"])) for a in soup.find_all("a", href=True) if DOC_EXT.search(a["href"])},
                  key=lambda x: x[1])


def fetch(url: str, timeout: int = 30) -> dict:
    """Fetch a URL. Returns {ok, status, html, error}; never raises."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
        blocked = r.status_code in (403, 503) and ("cloudflare" in r.text.lower() or "attention required" in r.text.lower())
        return {"ok": r.status_code < 400 and not blocked, "status": r.status_code, "html": r.text,
                "error": "blocked by Cloudflare bot check" if blocked else (None if r.status_code < 400 else f"HTTP {r.status_code}")}
    except requests.RequestException as e:
        return {"ok": False, "status": None, "html": "", "error": type(e).__name__}
