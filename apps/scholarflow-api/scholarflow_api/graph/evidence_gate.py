"""Topic query cleaning + evidence relevance gate for research workflows.

Deterministic heuristics only — no LLM-invented relevance scores.
Papers are graded core | supporting | irrelevant for specialized topics
(e.g. compressed sensing); other topics keep a binary score→core mapping.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from scholarflow_api.chat.paper_rank import score_paper

RelevanceTier = Literal["core", "supporting", "irrelevant"]

# Instructional / boilerplate fragments that pollute arXiv queries.
_BOILERPLATE = re.compile(
    r"("
    r"检索相关论文|研究问题|核心方法|创新点|局限性|"
    r"查找并分析|相关\s*GitHub|开源实现|技术框架|主要模块|可复现性|"
    r"并据此设计|实验方案|对照实验|消融实验|评价指标|"
    r"证据审查|结果汇总|Baseline|最后进行|"
    r"retrieve related papers|design an experiment|evidence review|"
    r"find.*github|open[- ]source implementation"
    r")",
    re.I,
)

_CN_EN = (
    ("图像压缩感知", "image compressed sensing"),
    ("压缩感知重建", "compressed sensing reconstruction"),
    ("压缩感知", "compressed sensing"),
    ("深度学习", "deep learning"),
    ("图像重建", "image reconstruction"),
    ("单像素成像", "single pixel imaging"),
    ("稀疏恢复", "sparse recovery"),
    ("混合检索", "hybrid retrieval"),
    ("检索增强", "retrieval augmented"),
)

_REPO_FROM_TEXT = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")

_TOPIC_REPO_HINTS: list[tuple[tuple[str, ...], str]] = [
    # Curated image-CS PyTorch implementation (verified via live API description).
    # Never langchain for this topic.
    (
        ("compressed sensing", "compressive sensing", "压缩感知"),
        "jianzhangcs/ISTA-Net-PyTorch",
    ),
    (
        ("hybrid rag", "retrieval augmented", "naive rag", "blended rag", "bm25"),
        "langchain-ai/langchain",
    ),
]

# Direct CS / reconstruction method markers (title/abstract/problem/method).
# Core = natural/optical image compressed-sensing reconstruction methods.
_CS_IMAGE_CORE_PHRASES = (
    "image compressive sensing",
    "image compressed sensing",
    "compressed sensing reconstruction",
    "compressive sensing reconstruction",
    "compressive sensing of images",
    "compressed sensing of images",
    "image cs reconstruction",
    "single-pixel imaging",
    "single pixel imaging",
    "ista-net",
    "admm-csnet",
    "admm-cs",
    "reconnet",
    "csnet",
    "cs-net",
    "opine-net",
    "amp-net",
)

# Supporting = related math / domain CS (MRI etc.) — not the primary image-CS task.
_CS_SUPPORTING_PHRASES = (
    "sparse recovery",
    "sparse reconstruction",
    "sparsity-based",
    "measurement matrix",
    "undersampled mri",
    "undersampled magnetic",
    "l1 minimization",
    "ℓ1 minimization",
    "basis pursuit",
    "compressed sensing",
    "compressive sensing",
    "structured compressed sensing",
)

_CS_DOMAIN_SUPPORTING = (
    "mri",
    "magnetic resonance",
    "clinical practice",
    "ultrasound localization",
    "medical imaging",
)

# Domain impostors that share "sensing" / "deep learning" / "image" tokens.
_CS_IRRELEVANT_PHRASES = (
    "remote sensing",
    "oriented object detection",
    "optical remote sensing",
    "thrombectomy",
    "ischemic stroke",
    "recanalization",
    "lecture notes",
    "github emoji",
    "github applications",
    "stack overflow",
    "developer collaboration",
    "ai agent systems",
    "image restoration network",  # alone not CS reconstruction
    "high-order degradation",
)

_PAREN_EN = re.compile(r"[（(]\s*([A-Za-z][^）)]{8,120})\s*[）)]")


def _dedupe_tokens(text: str) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for tok in text.split():
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tok)
    return " ".join(out)


def extract_short_topic_title(question: str, *, max_len: int = 64) -> str:
    """Human-readable short title for task UI / research_plan.title (not the full brief)."""
    q = (question or "").strip()
    if not q:
        return "ScholarFlow research"
    # Prefer English gloss in parentheses.
    m = _PAREN_EN.search(q)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip(" -_,;.")
        if 8 <= len(title) <= max_len:
            return title
    head = q
    for sep in ("：", ":", "；", ";"):
        if sep in head:
            head = head.split(sep, 1)[0].strip()
            break
    head = re.sub(r"[（(][^）)]*[）)]", "", head).strip()
    for cn, en in _CN_EN:
        if cn in head:
            return en[:max_len]
    if len(head) > max_len:
        head = head[:max_len].rstrip()
    return head or "ScholarFlow research"


def extract_paper_query(question: str, *, max_len: int = 120) -> str:
    """Derive a short arXiv-friendly query from a long user instruction.

    Never use the full Chinese brief as the sole search string.
    """
    raw = (question or "").strip()
    if not raw:
        return "research survey"

    # 1) Prefer explicit English topic in parentheses, but collapse title-like
    # glosses into searchable keywords (not a verbatim long paper title).
    m = _PAREN_EN.search(raw)
    if m:
        en = _dedupe_tokens(re.sub(r"\s+", " ", m.group(1)).strip(" -_,;."))
        en_l = en.lower()
        if "compressed sensing" in en_l or "compressive sensing" in en_l:
            # Favor image-CS reconstruction terms for arXiv relevance ranking.
            return "image compressed sensing reconstruction deep learning"[:max_len]
        if len(en) >= 8:
            if len(en) > max_len:
                en = en[:max_len].rsplit(" ", 1)[0] or en[:max_len]
            return en

    q = raw
    for cn, en in _CN_EN:
        q = q.replace(cn, en)

    if "：" in q:
        head = q.split("：", 1)[0].strip()
        if 4 <= len(head) <= 100:
            q = head
    elif ":" in q and len(q) > 80:
        head = q.split(":", 1)[0].strip()
        if 4 <= len(head) <= 100 and not head.lower().startswith("http"):
            q = head

    q = _BOILERPLATE.sub(" ", q)
    q = re.sub(r"[，。；、（）【】\[\]{}]", " ", q)
    q = re.sub(r"\s+", " ", q).strip(" -_,;.")

    latin = " ".join(re.findall(r"[A-Za-z][A-Za-z0-9+./-]{1,}", q))
    if len(latin) >= 8:
        q = latin

    q = _dedupe_tokens(q)
    # Drop leftover instructional English tokens.
    drop = {
        "baseline",
        "github",
        "analyze",
        "analysis",
        "generate",
        "report",
        "evidence",
        "review",
        "design",
        "experiment",
    }
    q = " ".join(t for t in q.split() if t.lower() not in drop)
    q = _dedupe_tokens(q)

    if len(q) > max_len:
        q = q[:max_len].rsplit(" ", 1)[0] or q[:max_len]
    return q or "image compressed sensing reconstruction"


def extract_repo_search_query(question: str) -> str:
    """GitHub search for image-CS implementations — never default to langchain/RAG."""
    # Avoid broad OR queries: GitHub ranks "compressed"/smuggling noise above ISTA-Net.
    if is_compressed_sensing_topic(question):
        return "image compressive sensing ISTA-Net language:Python stars:>10"
    paper_q = extract_paper_query(question, max_len=80)
    return f"{paper_q} language:Python stars:>10"


def suggest_hardcoded_repo(question: str) -> str | None:
    """Optional curated hint — empty string means 'no default repo for this topic'."""
    blob = (question or "").lower()
    for keys, repo in _TOPIC_REPO_HINTS:
        if any(k in blob for k in keys):
            return repo or None
    m = _REPO_FROM_TEXT.search(question or "")
    if m and not m.group(1).lower().startswith("http"):
        return m.group(1)
    return None


def is_compressed_sensing_topic(question: str) -> bool:
    text = f"{(question or '').lower()} {extract_paper_query(question).lower()}"
    return any(
        t in text
        for t in (
            "compressed sensing",
            "compressive sensing",
            "压缩感知",
            "single pixel",
            "单像素",
        )
    )


def requires_core_paper_evidence(question: str) -> bool:
    """Topics where supporting-only evidence must not drive a successful report."""
    return is_compressed_sensing_topic(question)


def _paper_text_blob(paper: dict[str, Any]) -> str:
    parts = [
        paper.get("title") or "",
        paper.get("abstract") or "",
        paper.get("research_problem") or "",
        paper.get("methodology") or "",
    ]
    return " ".join(parts).lower()


def classify_paper_relevance(
    question: str, paper: dict[str, Any]
) -> tuple[RelevanceTier, float, list[str]]:
    """Grade a paper for the current question.

    Uses title + abstract + research_problem + methodology (real fields only).
    Score from ``score_paper`` is retained for ranking — tier is not a fabricated score.
    """
    query = extract_paper_query(question)
    score, signals = score_paper(query, paper)
    reasons: list[str] = list(signals)
    blob = _paper_text_blob(paper)
    title = (paper.get("title") or "").lower()

    if not is_compressed_sensing_topic(question):
        # Non-CS topics: legacy binary gate → core | irrelevant.
        ok = score >= (4.0 if len(query) < 40 else 3.0) or any(
            s.startswith("title_phrase:") for s in signals
        )
        if ok:
            return "core", score, reasons + ["tier:core_via_legacy_score"]
        return "irrelevant", score, reasons + ["tier:irrelevant_via_legacy_score"]

    # --- Image compressed-sensing specialized grading ---
    # Remote-sensing restoration / medical impostors: never core for image-CS tasks.
    if any(bad in blob for bad in _CS_IRRELEVANT_PHRASES):
        if any(p in blob for p in ("compressed sensing", "compressive sensing")) and not any(
            x in blob for x in ("remote sensing", "thrombectomy", "lecture notes")
        ):
            # e.g. MRI CS still supporting below — fall through
            reasons.append("tier_note:domain_marker_with_cs")
        else:
            return (
                "irrelevant",
                score,
                reasons + ["tier:irrelevant_domain_impostor"],
            )

    has_image_cs_core = any(p in blob for p in _CS_IMAGE_CORE_PHRASES)
    if not has_image_cs_core and (
        ("image" in blob or "natural image" in blob or "optical image" in blob)
        and any(p in blob for p in ("compressed sensing", "compressive sensing"))
        and any(x in blob for x in ("reconstruc", "recovery", "deep", "network", "cnn", "unet"))
    ):
        has_image_cs_core = True
        reasons.append("tier_signal:image+cs+recon_or_network")

    # Medical / ultrasound / clinical CS is supporting for *image* CS reconstruction goals.
    domain_support = any(d in blob for d in _CS_DOMAIN_SUPPORTING)
    if has_image_cs_core and domain_support and not any(
        p in blob for p in ("natural image", "optical image", "single-pixel", "single pixel")
    ):
        # MRI CS tutorial etc. — useful background, not core image-CS evidence.
        return (
            "supporting",
            score,
            reasons + ["tier:supporting_domain_cs_not_natural_image"],
        )

    if has_image_cs_core:
        return "core", score, reasons + ["tier:core_image_cs_reconstruction"]

    has_supporting = any(p in blob for p in _CS_SUPPORTING_PHRASES) or domain_support
    if has_supporting:
        return (
            "supporting",
            score,
            reasons + ["tier:supporting_sparse_or_generic_cs"],
        )

    if "deep learning" in title or "deep learning" in blob:
        reasons.append("reject:deep_learning_only_overlap")
    return "irrelevant", score, reasons + ["tier:irrelevant_no_cs_substance"]

def paper_is_relevant(question: str, paper: dict[str, Any]) -> tuple[bool, float, list[str]]:
    tier, score, signals = classify_paper_relevance(question, paper)
    ok = tier in {"core", "supporting"}
    return ok, score, signals


def filter_relevant_papers(
    question: str, papers: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for p in papers:
        tier, score, signals = classify_paper_relevance(question, p)
        item = dict(p)
        item["relevance_score"] = round(score, 3)
        item["relevance_signals"] = signals
        item["relevance_tier"] = tier
        item["relevance_reason"] = "; ".join(signals[-4:]) if signals else tier
        item["relevance_accepted"] = tier in {"core", "supporting"}
        if tier in {"core", "supporting"}:
            accepted.append(item)
        else:
            rejected.append(item)

    def _sort_key(x: dict[str, Any]) -> tuple[int, float]:
        tier_rank = 0 if x.get("relevance_tier") == "core" else 1
        return (tier_rank, -float(x.get("relevance_score") or 0))

    accepted.sort(key=_sort_key)
    return accepted, rejected


def papers_by_tier(
    papers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    core = [p for p in papers if (p.get("relevance_tier") or "core") == "core"]
    supporting = [p for p in papers if p.get("relevance_tier") == "supporting"]
    return core, supporting


def select_papers_for_workflow(
    papers: list[dict[str, Any]], *, limit: int = 5
) -> list[dict[str, Any]]:
    """Prefer core, then supporting; never promote irrelevant."""
    core, supporting = papers_by_tier(papers)
    out = list(core) + list(supporting)
    return out[: max(0, limit)]


_REPO_CS_MARKERS = (
    "compressive sensing",
    "compressed sensing",
    "image compressive",
    "image compressed",
    "ista-net",
    "ista_net",
    "admm-cs",
    "admm-csnet",
    "csnet",
    "opine-net",
    "amp-net",
    "reconnet",
)


def repo_is_relevant(question: str, repo: dict[str, Any]) -> tuple[bool, float, list[str]]:
    query = extract_paper_query(question)
    # Score against description+readme, not bare owner/name (avoids empty title_phrase).
    desc = (repo.get("description") or "").strip()
    arch = (repo.get("architecture_summary") or "").strip()
    name = (repo.get("repository") or "").strip()
    blob = f"{name} {desc} {arch}".strip()
    fake_paper = {
        "title": desc or name,
        "abstract": blob,
        "year": None,
    }
    score, signals = score_paper(query, fake_paper)
    name_l = name.lower()
    blob_l = blob.lower()
    q_l = query.lower()
    if any(t in q_l for t in ("compressed sensing", "compressive sensing", "image reconstruction")):
        if ("langchain" in name_l or "rag" in name_l) and "sensing" not in blob_l:
            if "compress" not in blob_l and "sensing" not in blob_l:
                return False, score, signals + ["reject:repo_theme_mismatch"]

    # CS topic: accept repos with explicit CS method markers even when
    # query uses "compressed" and README uses "compressive" (score_paper synonym gap).
    if is_compressed_sensing_topic(question):
        if any(m in blob_l for m in _REPO_CS_MARKERS) or (
            "ista" in blob_l and ("sensing" in blob_l or "compress" in blob_l)
        ):
            return True, max(score, 3.0), signals + ["accept:repo_cs_markers"]
        if "langchain" in name_l or ("rag" in name_l and "sensing" not in blob_l):
            return False, score, signals + ["reject:repo_theme_mismatch"]
        # No CS substance — reject regardless of weak token overlap (e.g. "image").
        return False, score, signals + ["reject:repo_lacks_cs_markers"]

    ok = score >= 2.5 or any(s.startswith("title_phrase:") for s in signals)
    if "langchain" in name_l and any(t in q_l for t in ("rag", "retrieval", "langchain")):
        ok = True
        signals = signals + ["accept:rag_langchain_hint"]
    return ok, score, signals


def filter_relevant_repos(
    question: str, repos: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for r in repos:
        ok, score, signals = repo_is_relevant(question, r)
        item = dict(r)
        item["relevance_score"] = round(score, 3)
        item["relevance_signals"] = signals
        item["relevance_accepted"] = ok
        item["relevance_tier"] = "core" if ok else "irrelevant"
        item["relevance_reason"] = "; ".join(signals[-3:]) if signals else ""
        (accepted if ok else rejected).append(item)
    return accepted, rejected


_FIXTURE_THEME_RAG = ("rag", "retrieval", "blended", "naive", "bm25", "langchain", "hybrid")
_CONFLICT_THEMES = (
    ("compressed sensing", "compressive sensing", "压缩感知", "image reconstruction", "单像素"),
)


def fixture_theme_compatible(question: str, *, fixture_theme: str = "rag") -> bool:
    """Reject using a themed fixture corpus for a clearly conflicting research topic."""
    blob = (question or "").lower()
    paper_q = extract_paper_query(question).lower()
    text = f"{blob} {paper_q}"
    if fixture_theme == "rag":
        if any(any(k in text for k in keys) for keys in _CONFLICT_THEMES):
            return False
        if any(k in text for k in _FIXTURE_THEME_RAG):
            return True
        return True
    return True


def strip_relevance_annotations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare items for schema persist; keep tier/reason as limitations tags."""
    drop = {"relevance_score", "relevance_signals", "relevance_accepted"}
    out: list[dict[str, Any]] = []
    for item in items:
        d = {k: v for k, v in item.items() if k not in drop and k not in {"relevance_tier", "relevance_reason"}}
        tier = item.get("relevance_tier")
        reason = item.get("relevance_reason") or ""
        if tier:
            lim = [str(x) for x in (d.get("limitations") or [])]
            tag = f"relevance_tier={tier}"
            if reason:
                tag = f"{tag}; {reason}"
            if not any(str(x).startswith("relevance_tier=") for x in lim):
                lim.append(tag)
            d["limitations"] = lim
        out.append(d)
    return out


def claims_from_question_and_evidence(
    question: str,
    papers: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build reviewable claims grounded in the current question + evidence ids."""
    q = extract_paper_query(question)
    core, supporting = papers_by_tier(papers)
    claims: list[dict[str, Any]] = []

    if requires_core_paper_evidence(question) and not core:
        claims.append(
            {
                "claim": f"Insufficient core evidence for: {q}",
                "related_evidence_ids": [],
                "kind": "insufficiency",
            }
        )
    elif core:
        claims.append(
            {
                "claim": f"Core papers are topically related to: {q}",
                "related_evidence_ids": [p.get("evidence_id") for p in core[:3]],
                "kind": "topic_alignment",
                "required_tier": "core",
            }
        )
        for p in core[:2]:
            claims.append(
                {
                    "claim": f"Core paper contributes to the topic: {p.get('title') or p.get('evidence_id')}",
                    "related_evidence_ids": [p.get("evidence_id")],
                    "kind": "paper_support",
                    "required_tier": "core",
                }
            )
    elif papers:
        # Non-CS topics may only have legacy-core mapping
        claims.append(
            {
                "claim": f"Retrieved papers are topically related to: {q}",
                "related_evidence_ids": [p.get("evidence_id") for p in papers[:3]],
                "kind": "topic_alignment",
            }
        )

    if supporting:
        claims.append(
            {
                "claim": f"Supporting papers are background only (not core) for: {q}",
                "related_evidence_ids": [p.get("evidence_id") for p in supporting[:2]],
                "kind": "supporting_background",
                "required_tier": "supporting",
            }
        )

    if repos:
        claims.append(
            {
                "claim": f"Repository evidence is related to: {q}",
                "related_evidence_ids": [r.get("evidence_id") for r in repos[:2]],
                "kind": "repo_alignment",
            }
        )
    if not claims:
        claims.append(
            {
                "claim": f"Insufficient evidence collected for: {q}",
                "related_evidence_ids": [],
                "kind": "insufficiency",
            }
        )
    return claims


def claim_supported_by_evidence(
    claim: dict[str, Any],
    papers: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    question: str,
) -> dict[str, Any]:
    """Deterministic claim check — never auto-support a fixed RAG slogan."""
    ids = [i for i in (claim.get("related_evidence_ids") or []) if i]
    kind = claim.get("kind") or "generic"
    required_tier = claim.get("required_tier")
    paper_by_id = {p.get("evidence_id"): p for p in papers}
    repo_by_id = {r.get("evidence_id"): r for r in repos}

    if kind == "insufficiency" or not ids:
        return {
            "claim": claim.get("claim"),
            "related_evidence_ids": ids,
            "status": "unverified",
            "reason": "insufficient_evidence: No linked evidence_ids for this claim",
            "recommended_action": "Re-run retrieval with a clearer topic query",
        }

    linked_papers = [paper_by_id[i] for i in ids if i in paper_by_id]
    linked_repos = [repo_by_id[i] for i in ids if i in repo_by_id]
    if not linked_papers and not linked_repos:
        return {
            "claim": claim.get("claim"),
            "related_evidence_ids": ids,
            "status": "unsupported",
            "reason": "Linked evidence_ids not present in upstream results",
            "recommended_action": "Fix evidence linkage before assemble",
        }

    bad: list[str] = []
    for p in linked_papers:
        tier, _, sigs = classify_paper_relevance(question, p)
        # Prefer annotated tier when present (already graded upstream).
        tier = p.get("relevance_tier") or tier
        if tier == "irrelevant":
            bad.append(f"{p.get('evidence_id')}:irrelevant")
            continue
        if required_tier == "core" and tier != "core":
            bad.append(f"{p.get('evidence_id')}:expected_core_got_{tier}")
        if required_tier == "supporting" and tier not in {"supporting", "core"}:
            bad.append(f"{p.get('evidence_id')}:expected_supporting_got_{tier}")
        if kind == "topic_alignment" and tier != "core" and requires_core_paper_evidence(question):
            bad.append(f"{p.get('evidence_id')}:topic_alignment_requires_core")
    for r in linked_repos:
        ok, _, sigs = repo_is_relevant(question, r)
        if not ok:
            bad.append(f"{r.get('evidence_id')}:irrelevant({','.join(sigs[-2:])})")

    if bad:
        return {
            "claim": claim.get("claim"),
            "related_evidence_ids": ids,
            "status": "unsupported",
            "reason": "Evidence tier/claim mismatch: " + "; ".join(bad),
            "recommended_action": "Use core evidence for core claims; drop irrelevant items",
        }

    return {
        "claim": claim.get("claim"),
        "related_evidence_ids": ids,
        "status": "supported",
        "reason": "Linked evidence present and matches required relevance tier",
        "recommended_action": "Proceed with caution; review remains rule-based (not LLM judge)",
    }
