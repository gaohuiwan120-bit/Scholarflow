"""Paper search post-processing: URL sanitize + lightweight relevance re-rank.

Uses only real title/abstract/research_problem fields from MCP/arXiv.
Does not invent authors, years, abstracts, or classic labels.
"""

from __future__ import annotations

import re
from typing import Any

# High-frequency terms that alone should not dominate relevance for specialized queries.
_WEAK_ALONE = frozenset(
    {
        "sparse",
        "sparsity",
        "recovery",
        "reconstruction",
        "signal",
        "signals",
        "sampling",
        "sample",
        "optimization",
        "algorithm",
        "algorithms",
        "learning",
        "network",
        "networks",
        "deep",
        "model",
        "models",
        "method",
        "methods",
        "based",
        "using",
        "via",
        "approach",
        "analysis",
        "study",
        "data",
        "image",
        "images",
        "paper",
        "arxiv",
    }
)

_SURVEY_MARKERS = ("survey", "review", "tutorial", "overview", "primer")
_MD_LINK = re.compile(r"^\[([^\]]*)\]\((https?://[^)\s]+)\)\s*$")
_URL_IN_TEXT = re.compile(r"https?://[^\s\]\)\"'<>]+")
_TOKEN = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}", re.I)


def sanitize_source_url(url: str | None) -> str:
    """Return a bare http(s) URL; strip Markdown link wrappers if present."""
    raw = (url or "").strip()
    if not raw:
        return ""
    md = _MD_LINK.match(raw)
    if md:
        raw = md.group(2)
    # If the whole field is polluted, take the first URL substring.
    if "://" not in raw[:12] and "http" in raw.lower():
        found = _URL_IN_TEXT.search(raw)
        if found:
            raw = found.group(0)
    raw = raw.rstrip(").,;]'\"")
    if raw.startswith("http://arxiv.org/"):
        raw = "https://" + raw[len("http://") :]
    return raw


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _is_broad_query(query: str, strong_terms: list[str]) -> bool:
    q = (query or "").strip()
    if len(q) <= 24 and len(strong_terms) <= 2:
        return True
    lowered = q.lower()
    broad_hints = ("关于", "找一找", "相关", "介绍", "什么是", "overview", "general")
    return any(h in lowered for h in broad_hints) and len(strong_terms) <= 3


def score_paper(query: str, paper: dict[str, Any]) -> tuple[float, list[str]]:
    """Return (score, human-readable signals from real field matches)."""
    title = (paper.get("title") or "").strip()
    abstract = (
        paper.get("abstract")
        or paper.get("research_problem")
        or ""
    ).strip()
    title_l = title.lower()
    abs_l = abstract.lower()
    q_l = (query or "").strip().lower()

    q_terms = _tokenize(query)
    strong = [t for t in q_terms if t not in _WEAK_ALONE and len(t) >= 3]
    weak = [t for t in q_terms if t in _WEAK_ALONE]

    score = 0.0
    signals: list[str] = []

    # Multi-word English phrase from query (length >= 2 tokens).
    phrase_candidates: list[str] = []
    if len(q_terms) >= 2:
        # contiguous bigrams / full english-ish query
        for i in range(len(q_terms) - 1):
            phrase_candidates.append(f"{q_terms[i]} {q_terms[i + 1]}")
        if 3 <= len(q_l) <= 80 and re.fullmatch(r"[a-z0-9\s\-]+", q_l):
            phrase_candidates.append(q_l)

    for phr in phrase_candidates:
        if len(phr) < 5:
            continue
        if phr in title_l:
            score += 6.0
            signals.append(f"title_phrase:{phr}")
            break
        if phr in abs_l:
            score += 3.0
            signals.append(f"abstract_phrase:{phr}")
            break

    title_hits = 0
    for t in strong:
        if t in title_l:
            score += 2.5
            title_hits += 1
        elif t in abs_l:
            score += 1.0
    if title_hits:
        signals.append(f"strong_title_terms:{title_hits}")

    # Weak terms alone should not dominate.
    weak_only_in_title = False
    if strong:
        strong_in_doc = any(t in title_l or t in abs_l for t in strong)
        weak_in_title = any(t in title_l for t in weak)
        if weak_in_title and not strong_in_doc:
            score -= 2.0
            weak_only_in_title = True
            signals.append("penalty:weak_terms_without_strong")
        elif weak_in_title and strong_in_doc:
            score += 0.3 * sum(1 for t in weak if t in title_l)
    else:
        # Query itself is mostly weak terms — still use them lightly.
        for t in weak:
            if t in title_l:
                score += 1.0
            elif t in abs_l:
                score += 0.4

    survey_in_title = any(m in title_l for m in _SURVEY_MARKERS)
    if survey_in_title:
        signals.append("title_marker:survey_or_review")
        if _is_broad_query(query, strong):
            score += 3.5
        else:
            score += 1.0

    # "remote sensing" / generic "sensing" must not satisfy "compressed sensing".
    # Treat compressed/compressive as synonyms for phrase matching.
    if "compress" in q_l or "compressive" in q_l:
        has_cs_title = ("compressed sensing" in title_l) or (
            "compressive sensing" in title_l
        )
        has_cs_abs = ("compressed sensing" in abs_l) or (
            "compressive sensing" in abs_l
        )
        if has_cs_title:
            score += 2.0
            signals.append("title_phrase:compressed/compressive sensing")
        elif has_cs_abs:
            score += 2.0
            signals.append("abstract_phrase:compressed/compressive sensing")
        elif "sensing" in title_l and "compress" not in title_l and "compressive" not in title_l:
            score -= 5.0
            signals.append("penalty:sensing_without_compress")
        elif not has_cs_abs and "sensing" in abs_l and "compress" not in abs_l:
            score -= 2.0
            signals.append("penalty:abstract_sensing_without_compress")

    # Prefer slightly newer papers as a tie-break only (real year field).
    year = paper.get("year")
    if isinstance(year, int) and 1990 <= year <= 2100:
        score += min(1.5, max(0.0, (year - 2005) / 20.0))

    if weak_only_in_title and score < 1.0:
        score = min(score, 0.5)

    return score, signals


def kind_hint_from_title(title: str | None) -> str | None:
    """Only label survey/review when the real title contains those words."""
    t = (title or "").lower()
    if any(m in t for m in _SURVEY_MARKERS):
        return "survey_or_review"
    return None


def rerank_papers(
    query: str,
    papers: list[dict[str, Any]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """Re-rank a candidate list; preserve original fields; add score metadata."""
    if not papers:
        return []
    scored: list[tuple[float, int, dict[str, Any], list[str]]] = []
    for idx, p in enumerate(papers):
        s, sigs = score_paper(query, p)
        scored.append((s, idx, p, sigs))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out: list[dict[str, Any]] = []
    for s, _idx, p, sigs in scored[: max(1, top_k)]:
        item = dict(p)
        item["relevance_score"] = round(float(s), 3)
        item["relevance_signals"] = sigs
        item["kind_hint"] = kind_hint_from_title(p.get("title"))
        url = sanitize_source_url(p.get("source_url"))
        if not url and p.get("identifier"):
            url = f"https://arxiv.org/abs/{p.get('identifier')}"
        item["source_url"] = url
        out.append(item)
    return out


def slim_paper_for_tool(p: dict[str, Any]) -> dict[str, Any]:
    """Compact tool payload: real fields only; empty when unknown."""
    authors = p.get("authors") or []
    if not isinstance(authors, list):
        authors = []
    authors = [str(a).strip() for a in authors if str(a).strip()][:12]
    abstract = (p.get("abstract") or p.get("research_problem") or "").strip()
    return {
        "evidence_id": p.get("evidence_id"),
        "identifier": p.get("identifier"),
        "title": p.get("title"),
        "authors": authors,
        "year": p.get("year"),
        "source_url": sanitize_source_url(p.get("source_url")),
        "abstract": abstract[:500] if abstract else "",
        "research_problem": (p.get("research_problem") or "")[:300],
        "kind_hint": p.get("kind_hint"),
        "relevance_score": p.get("relevance_score"),
        "relevance_signals": p.get("relevance_signals") or [],
    }
