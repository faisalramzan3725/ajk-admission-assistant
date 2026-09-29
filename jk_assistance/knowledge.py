"""Policy-aware knowledge layer.

Two parts:
  * Structured, versioned knowledge (knowledge/*.yaml): institutions, services, fees with effective dates,
    admission programs, deadlines and progression rules. Used by the deterministic engines.
  * Evidence corpus: every curated YAML entry plus the text of every fetched page and document
    (raw/**/*.txt, documents/**/text/*.txt), chunked and indexed with BM25 for retrieval-augmented answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from rank_bm25 import BM25Okapi

from .config import DOCUMENTS_DIR, KNOWLEDGE_DIR, RAW_DIR, ROOT

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = set("a an the of to in on for and or is are be by with at from as it this that i my me how what which do does can "
                "will shall should into your you we our their there any all per".split())

# Minimum characters for a fetched page/document to be indexed (skips empty or blocked captures).
MIN_DOC_CHARS = 200


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
    kind: str  # service | program | deadline | rule | institution | page | document
    trust: str = "official"
    meta: dict = field(default_factory=dict)


class Knowledge:
    def __init__(self):
        self.institutions = {i["id"]: i for i in _load("institutions.yaml")["institutions"]}
        self.services = {s["id"]: s for s in _load("services.yaml")["services"]}
        adm = _load("admissions.yaml")
        self.admissions = adm
        self.programs = {p["id"]: p for p in adm["programs"]}
        dl = _load("deadlines.yaml")
        self.dated_deadlines = dl["dated"]
        self.relative_rules = {r["id"]: r for r in dl["relative_rules"]}
        self.academic_calendar = dl.get("academic_calendar", {})
        self.rule_sets = {r["id"]: r for r in _load("progression_rules.yaml")["rule_sets"]}
        self.chunks = self._build_corpus()
        self._bm25 = BM25Okapi([tokenize(c.text) for c in self.chunks])

    # ------------------------------------------------------------------ versioned fees
    @staticmethod
    def fee_version(fee: dict, on: date) -> dict | None:
        """Newest fee version whose effective_from <= on. Falls back to the earliest one (flagged) if all are later."""
        versions = sorted(fee["versions"], key=lambda v: _as_date(v["effective_from"]))
        applicable = [v for v in versions if _as_date(v["effective_from"]) <= on]
        if applicable:
            chosen = dict(applicable[-1])
            chosen["superseded"] = [v for v in versions if v is not applicable[-1] and _as_date(v["effective_from"]) < _as_date(chosen["effective_from"])]
            return chosen
        chosen = dict(versions[0])
        chosen["future_only"] = True
        return chosen

    def service_fees(self, service_id: str, on: date) -> list[dict]:
        out = []
        for fee in self.services[service_id].get("fees", []):
            v = self.fee_version(fee, on)
            out.append({"item": fee["item"], **{k: v[k] for k in v if k != "superseded"},
                        "previous_versions": [{"amount": p["amount"], "effective_from": str(p["effective_from"])} for p in v.get("superseded", [])]})
        return out

    # ------------------------------------------------------------------ lookup helpers
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

    def match_services(self, text: str, institution: str | None = None, limit: int = 3) -> list[tuple[float, dict]]:
        """Keyword match of a question against service keywords (deterministic, used before retrieval)."""
        q = " " + " ".join(tokenize(text)) + " "
        scored = []
        for s in self.services.values():
            if institution and s["institution"] != institution:
                continue
            score = 0.0
            for kw in s.get("keywords", []):
                k = " ".join(tokenize(kw))
                if k and f" {k} " in q:
                    score = max(score, 1.0 + 0.25 * len(k.split()))
            if score:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return scored[:limit]

    # ------------------------------------------------------------------ retrieval
    def search(self, query: str, institution: str | None = None, k: int = 6, kinds: set[str] | None = None) -> list[tuple[float, Chunk]]:
        scores = self._bm25.get_scores(tokenize(query))
        ranked = []
        for score, chunk in zip(scores, self.chunks):
            if score <= 0:
                continue
            if kinds and chunk.kind not in kinds:
                continue
            if institution and chunk.institution not in (institution, None):
                continue
            boost = 1.3 if chunk.kind in {"service", "program", "rule", "deadline", "institution"} else 1.0
            boost *= 0.8 if chunk.trust == "secondary" else 1.0
            ranked.append((score * boost, chunk))
        ranked.sort(key=lambda x: -x[0])
        return ranked[:k]

    # ------------------------------------------------------------------ corpus
    def _build_corpus(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for iid, inst in self.institutions.items():
            chunks.append(Chunk(f"inst:{iid}", yaml.safe_dump(inst, allow_unicode=True, sort_keys=False), inst.get("website", ""), iid, "institution", inst.get("trust", "official")))
        for sid, s in self.services.items():
            chunks.append(Chunk(f"service:{sid}", f"{s['name']} ({self.institutions[s['institution']]['name']})\n" + yaml.safe_dump(s, allow_unicode=True, sort_keys=False),
                                (s.get("sources") or [""])[0], s["institution"], "service", s.get("trust", "official")))
        for pid, p in self.programs.items():
            chunks.append(Chunk(f"program:{pid}", f"Admission program: {p['name']}\n" + yaml.safe_dump(p, allow_unicode=True, sort_keys=False),
                                "knowledge/admissions.yaml", p["institution"], "program"))
        for inst_id, proc in self.admissions["application_process"].items():
            iid = "jac" if inst_id == "jac_medical" else inst_id
            chunks.append(Chunk(f"admission:{inst_id}", f"How to apply for admission - {self.institutions[iid]['name']}\n" + yaml.safe_dump(proc, allow_unicode=True, sort_keys=False),
                                (proc.get("sources") or [""])[0], iid, "program", "secondary" if "secondary" in str(proc.get("trust", "")) and iid == "jac" else "official"))
        for tid, t in self.admissions["tests"].items():
            chunks.append(Chunk(f"test:{tid}", f"Entry test: {t['name']}\n" + yaml.safe_dump(t, allow_unicode=True, sort_keys=False), t.get("source", ""), None, "program", t.get("trust", "official")))
        for d in self.dated_deadlines:
            chunks.append(Chunk(f"deadline:{d['id']}", f"Deadline {d['date']}: {d['title']}. {d.get('action', '')}", d["source"], d["institution"], "deadline", d.get("trust", "official")))
        for r in self.relative_rules.values():
            chunks.append(Chunk(f"deadline_rule:{r['id']}", f"Deadline rule: {r['title']} - {r['rule']}", r["source"], r["institution"], "deadline", r.get("trust", "official")))
        for rs in self.rule_sets.values():
            chunks.append(Chunk(f"rules:{rs['id']}", f"Academic progression rules: {rs['title']}\n" + yaml.safe_dump(rs, allow_unicode=True, sort_keys=False),
                                rs.get("source", ""), rs["institution"], "rule", rs.get("trust", "official")))
        chunks.extend(self._file_chunks())
        return chunks

    def _file_chunks(self) -> list[Chunk]:
        chunks = []
        files = list(RAW_DIR.rglob("*.txt")) + list(DOCUMENTS_DIR.rglob("text/*.txt"))
        for f in sorted(files):
            text = f.read_text(encoding="utf-8", errors="ignore")
            if len(text.strip()) < MIN_DOC_CHARS:
                continue
            rel = f.relative_to(ROOT).as_posix()
            m = re.match(r"SOURCE[^:]*:\s*(\S+)", text)
            source = m.group(1) if m else rel
            parts = rel.split("/")
            inst = parts[1] if parts[1] in self.institutions else None
            trust = "secondary" if "secondary" in parts else "official"
            kind = "page" if parts[0] == "raw" else "document"
            for n, piece in enumerate(_split(text)):
                chunks.append(Chunk(f"{rel}#{n}", piece, source if source.startswith("http") else rel, inst, kind, trust, {"file": rel}))
        return chunks


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


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


@lru_cache(maxsize=1)
def get_knowledge() -> Knowledge:
    return Knowledge()
