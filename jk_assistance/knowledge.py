"""Admission knowledge layer.

* Structured knowledge (knowledge/*.yaml): institutions, entry tests (with max marks and passing marks),
  programs (eligibility, test rules, fees), application processes and the admission calendar.
* Evidence corpus: the YAML entries plus every fetched admission page/document (raw/**/*.txt,
  documents/**/text/*.txt), chunked and indexed with BM25 for grounded answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml
from rank_bm25 import BM25Okapi

from .config import DOCUMENTS_DIR, KNOWLEDGE_DIR, RAW_DIR, ROOT

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = set("a an the of to in on for and or is are be by with at from as it this that i my me how what which do does can "
                "will shall should into your you we our their there any all per".split())
MIN_DOC_CHARS = 200  # skip empty / blocked captures


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def _load(name: str) -> dict:
    return yaml.safe_load((KNOWLEDGE_DIR / name).read_text(encoding="utf-8"))


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    institution: str | None
    kind: str  # program | test | process | deadline | institution | page | document
    trust: str = "official"
    meta: dict = field(default_factory=dict)


class Knowledge:
    def __init__(self):
        self.institutions = {i["id"]: i for i in _load("institutions.yaml")["institutions"]}
        adm = _load("admissions.yaml")
        self.groups = adm["groups"]
        self.tests = adm["tests"]
        self.processes = adm["application_process"]
        self.programs = {p["id"]: p for p in adm["programs"]}
        dl = _load("deadlines.yaml")
        self.dated_deadlines = dl["dated"]
        self.rules = dl["rules"]
        self.chunks = self._build_corpus()
        self._bm25 = BM25Okapi([tokenize(c.text) for c in self.chunks])

    def detect_institution(self, text: str) -> str | None:
        t = " " + text.lower() + " "
        best, best_len = None, 0
        for iid, inst in self.institutions.items():
            for alias in [iid] + inst.get("aliases", []):
                if alias == "must":  # also an English word - only the acronym counts
                    hit = re.search(r"\bMUST\b", text)
                else:
                    hit = re.search(r"\b" + re.escape(alias.lower()) + r"\b", t)
                if hit and len(alias) > best_len:
                    best, best_len = iid, len(alias)
        return best

    def detect_test(self, text: str) -> str | None:
        t = text.lower()
        for tid, pat in (("mdcat", r"\bmdcat\b"), ("ecat", r"\becat\b"), ("must_seet", r"\bseet\b"), ("hec_lat", r"\blat\b|law admission test"),
                         ("uajk_entry_test", r"uajk (entry )?test|entry test")):
            if re.search(pat, t):
                return tid
        return None

    def search(self, query: str, institution: str | None = None, k: int = 6) -> list[tuple[float, Chunk]]:
        scores = self._bm25.get_scores(tokenize(query))
        ranked = []
        for score, chunk in zip(scores, self.chunks):
            if score <= 0 or (institution and chunk.institution not in (institution, None)):
                continue
            boost = 1.3 if chunk.kind in {"program", "test", "process", "deadline", "institution"} else 1.0
            boost *= 0.8 if chunk.trust == "secondary" else 1.0
            ranked.append((score * boost, chunk))
        ranked.sort(key=lambda x: -x[0])
        return ranked[:k]

    def _build_corpus(self) -> list[Chunk]:
        dump = lambda o: yaml.safe_dump(o, allow_unicode=True, sort_keys=False)  # noqa: E731
        chunks = [Chunk(f"inst:{i}", dump(v), v.get("website", ""), i, "institution", "official") for i, v in self.institutions.items()]
        chunks += [Chunk(f"test:{t}", f"Entry test {v['name']}\n" + dump(v), (v.get("sources") or [""])[0], None, "test",
                         "official" if str(v.get("trust", "official")).startswith("official") else "secondary") for t, v in self.tests.items()]
        chunks += [Chunk(f"process:{i}", f"How to apply - {self.institutions[i]['name']}\n" + dump(v), (v.get("sources") or [""])[0], i, "process",
                         "official") for i, v in self.processes.items()]
        chunks += [Chunk(f"program:{p}", f"Admission program {v['name']} ({self.institutions[v['institution']]['name']})\n" + dump(v),
                         "knowledge/admissions.yaml", v["institution"], "program") for p, v in self.programs.items()]
        chunks += [Chunk(f"deadline:{d['id']}", f"Admission date {d['date']}: {d['title']}. {d.get('action', '')}", d["source"],
                         d["institution"], "deadline", d.get("trust", "official")) for d in self.dated_deadlines]
        chunks += [Chunk(f"rule:{r['id']}", f"Admission rule: {r['title']} - {r['rule']}", r["source"], r["institution"], "deadline") for r in self.rules]
        chunks += self._file_chunks()
        return chunks

    def _file_chunks(self) -> list[Chunk]:
        out = []
        for f in sorted(list(RAW_DIR.rglob("*.txt")) + list(DOCUMENTS_DIR.rglob("text/*.txt"))):
            text = f.read_text(encoding="utf-8", errors="ignore")
            if len(text.strip()) < MIN_DOC_CHARS:
                continue
            rel = f.relative_to(ROOT).as_posix()
            m = re.match(r"SOURCE[^:]*:\s*(\S+)", text)
            source = m.group(1) if m else rel
            parts = rel.split("/")
            inst = parts[1] if parts[1] in self.institutions else None
            trust = "secondary" if "secondary" in parts else "official"
            for n, piece in enumerate(_split(text)):
                out.append(Chunk(f"{rel}#{n}", piece, source if source.startswith("http") else rel, inst,
                                 "page" if parts[0] == "raw" else "document", trust, {"file": rel}))
        return out


def _split(text: str, size: int = 1400, overlap: int = 200) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    if len(text) <= size:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        cut = text.rfind("\n", start + size // 2, end)
        end = cut if cut > 0 and end < len(text) else end
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


@lru_cache(maxsize=1)
def get_knowledge() -> Knowledge:
    return Knowledge()
