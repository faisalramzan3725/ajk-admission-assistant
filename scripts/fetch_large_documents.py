"""Download the two large prospectus PDFs that are not committed to git (their extracted text is).

Usage: python scripts/fetch_large_documents.py
"""
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "documents/uajk/UAJK_Prospectus.pdf": "https://drive.usercontent.google.com/download?id=11p1lmnvh8MQiTETVNrAfmgaX25Wrg-kF&export=download&confirm=t",
    "documents/must/MUST_Prospectus_2024_25.pdf": "https://must.edu.pk/wp-content/uploads/2024/11/E-Prospectus_2024-25.pdf",
}

for rel, url in FILES.items():
    out = ROOT / rel
    if out.exists():
        print(f"exists  {rel}")
        continue
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
    r.raise_for_status()
    out.write_bytes(r.content)
    print(f"saved   {rel} ({len(r.content) / 1e6:.1f} MB)")
