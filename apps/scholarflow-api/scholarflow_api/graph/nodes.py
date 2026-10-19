"""LangGraph node implementations for ScholarFlow research agents."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from scholarflow_api.config import ensure_harness_on_path
from scholarflow_api.graph.adapters import (
    assemble_via_mcp,
    fetch_papers_via_mcp,
    load_fixture_papers,
    load_fixture_repositories,
    resolve_live_repository,
)
from scholarflow_api.graph.evidence_gate import (
    claim_supported_by_evidence,
    claims_from_question_and_evidence,
    extract_paper_query,
    extract_repo_search_query,
    extract_short_topic_title,
    filter_relevant_papers,
    filter_relevant_repos,
    fixture_theme_compatible,
    is_compressed_sensing_topic,
    papers_by_tier,
    requires_core_paper_evidence,
    select_papers_for_workflow,
    strip_relevance_annotations,
)
from scholarflow_api.graph.state import ResearchState, SubtaskRecord
from scholarflow_api.mcp.client import ScholarMcpError

logger = logging.getLogger("scholarflow_api.graph.nodes")


def _event(kind: str, **payload: Any) -> dict[str, Any]:
    return {"ts": time.time(), "kind": kind, **payload}


def _sleep_work(seconds: float) -> None:
    if seconds and seconds > 0:
        time.sleep(seconds)


def orchestrator_node(state: ResearchState) -> dict[str, Any]:
    """Parse task into ResearchPlan and declare explicit dependencies."""
    question = state["question"]
    mode = state.get("workflow_mode") or "research_orchestration"
    task_id = state["task_id"]
    paper_q = extract_paper_query(question)
    repo_q = extract_repo_search_query(question)
    short_title = extract_short_topic_title(question)
    plan = {
        "task_id": task_id,
        "title": short_title,
        "objective": question,
        "research_questions": [
            f"What methods and open implementations advance: {short_title}?",
        ],
        "search_queries": [
            paper_q,
            f"{paper_q} reconstruction",
            "image compressive sensing deep learning",
        ],
        "code_search_queries": [repo_q],
        "date_range": {"start": None, "end": None},
        "expected_outputs": [
            "research_report.md",
            "research_plan.json",
            "paper_evidence.json",
            "paper_matrix.csv",
            "repository_evidence.json",
            "repository_matrix.csv",
            "experiment_plan.md",
            "evidence_review.json",
            "sources.json",
        ],
        "completion_criteria": [
            "papers_with_source_url",
            "repositories_with_source_url",
            "experiment_plan_present",
            "review_pass_or_partial",
        ],
        "workflow_mode": mode,
        "dependencies": {
            "paper_research": [],
            "repository_analysis": [],
            "experiment_design": ["paper_research", "repository_analysis"],
            "review": ["experiment_design"],
            "assemble": ["review"],
        },
    }
    return {
        "research_plan": plan,
        "events": [_event("orchestrator_done", mode=mode, task_id=task_id)],
        "subtasks": [
            {
                "subtask_id": f"{task_id}-orchestrator",
                "role": "orchestrator",
                "status": "succeeded",
                "depends_on": [],
                "started_at": time.time(),
                "ended_at": time.time(),
                "duration_ms": 0,
                "summary": f"Planned workflow_mode={mode}",
                "data_source": "deterministic",
            }
        ],
    }


def paper_research_node(state: ResearchState) -> dict[str, Any]:
    """Paper research agent — may run in parallel with repository_analysis."""
    started = time.time()
    sub_id = f"{state['task_id']}-paper"
    work = float(state.get("simulate_work_seconds") or 0.0)
    events = [_event("paper_started", subtask_id=sub_id, started_at=started)]

    if state.get("force_fail_paper"):
        ended = time.time()
        rec: SubtaskRecord = {
            "subtask_id": sub_id,
            "role": "paper_research",
            "status": "failed",
            "depends_on": [],
            "started_at": started,
            "ended_at": ended,
            "duration_ms": int((ended - started) * 1000),
            "error": "Forced paper failure (test hook)",
            "data_source": "none",
        }
        return {
            "papers": [],
            "subtasks": [rec],
            "events": events + [_event("paper_failed", subtask_id=sub_id)],
        }

    _sleep_work(work)
    artifacts_dir = Path(state["artifacts_dir"])
    data_mode = state.get("data_mode") or "fixture"
    question = state["question"]
    paper_query = extract_paper_query(question)
    papers: list[dict[str, Any]] = []
    rejected_papers: list[dict[str, Any]] = []
    data_source = "fixture"
    mcp_calls: list[dict[str, Any]] = []
    degradation: list[dict[str, Any]] = []

    def _fail_paper(error: str, source: str) -> dict[str, Any]:
        ended = time.time()
        return {
            "papers": [],
            "subtasks": [
                {
                    "subtask_id": sub_id,
                    "role": "paper_research",
                    "status": "failed",
                    "depends_on": [],
                    "started_at": started,
                    "ended_at": ended,
                    "duration_ms": int((ended - started) * 1000),
                    "error": error,
                    "data_source": source,
                }
            ],
            "mcp_calls": mcp_calls,
            "degradation_events": degradation,
            "events": events
            + [
                _event(
                    "paper_failed",
                    error=error,
                    query=paper_query,
                    rejected=len(rejected_papers),
                )
            ],
        }

    if data_mode == "live":
        try:
            raw_papers, mcp_calls = fetch_papers_via_mcp(paper_query, max_results=12)
            papers, rejected_papers = filter_relevant_papers(question, raw_papers)
            data_source = "live_mcp"
            # If specialized topics yield zero CORE hits, try a shorter topical query once.
            if requires_core_paper_evidence(question):
                core_n = sum(1 for p in papers if p.get("relevance_tier") == "core")
                if core_n == 0:
                    alt_q = "image compressive sensing deep learning reconstruction"
                    if alt_q != paper_query:
                        raw2, calls2 = fetch_papers_via_mcp(alt_q, max_results=12)
                        mcp_calls = list(mcp_calls) + list(calls2)
                        p2, r2 = filter_relevant_papers(question, raw2)
                        papers, rejected_papers = p2, r2
                        paper_query = alt_q
            if not papers:
                return _fail_paper(
                    f"live MCP returned results but none passed "
                    f"topic relevance for query={paper_query!r}",
                    "live_mcp",
                )
            papers = select_papers_for_workflow(papers, limit=5)
            core_n = sum(1 for p in papers if p.get("relevance_tier") == "core")
            if requires_core_paper_evidence(question) and core_n == 0:
                return _fail_paper(
                    f"insufficient core evidence for query={paper_query!r}: "
                    f"accepted supporting/irrelevant only; rejected={len(rejected_papers)}",
                    "live_mcp",
                )
        except ScholarMcpError as exc:
            if state.get("allow_fixture_fallback"):
                if not fixture_theme_compatible(question, fixture_theme="rag"):
                    return _fail_paper(
                        f"live MCP failed ({exc}); RAG fixture fallback rejected as "
                        f"off-topic for query={paper_query!r}",
                        "fixture_degraded_from_live",
                    )
                raw_fix = load_fixture_papers(artifacts_dir)
                papers, rejected_papers = filter_relevant_papers(question, raw_fix)
                if not papers and fixture_theme_compatible(question, fixture_theme="rag"):
                    papers = [
                        {
                            **p,
                            "relevance_tier": "core",
                            "relevance_reason": "fixture_theme_compatible_default_core",
                            "relevance_accepted": True,
                        }
                        for p in raw_fix
                    ]
                    rejected_papers = []
                if not papers:
                    return _fail_paper(
                        f"live MCP failed ({exc}); fixture fallback rejected as "
                        f"off-topic for query={paper_query!r}",
                        "fixture_degraded_from_live",
                    )
                data_source = "fixture_degraded_from_live"
                degradation.append(
                    {
                        "ts": time.time(),
                        "node": "paper_research",
                        "reason": str(exc),
                        "action": "fixture_fallback_topic_checked",
                        "query": paper_query,
                    }
                )
            else:
                return _fail_paper(f"live MCP failed: {exc}", "live_mcp")
    else:
        if not fixture_theme_compatible(question, fixture_theme="rag"):
            return _fail_paper(
                f"fixture papers are off-topic for query={paper_query!r}",
                "fixture",
            )
        raw_fix = load_fixture_papers(artifacts_dir)
        papers, rejected_papers = filter_relevant_papers(question, raw_fix)
        if not papers and fixture_theme_compatible(question, fixture_theme="rag"):
            papers = [
                {
                    **p,
                    "relevance_tier": "core",
                    "relevance_reason": "fixture_theme_compatible_default_core",
                    "relevance_accepted": True,
                }
                for p in raw_fix
            ]
            rejected_papers = []
        data_source = "fixture"
        if not papers:
            return _fail_paper(
                f"fixture papers are off-topic for query={paper_query!r}",
                "fixture",
            )
        papers = select_papers_for_workflow(papers, limit=5)

    ended = time.time()
    core_papers, supporting_papers = papers_by_tier(papers)
    rec = {
        "subtask_id": sub_id,
        "role": "paper_research",
        "status": "succeeded",
        "depends_on": [],
        "started_at": started,
        "ended_at": ended,
        "duration_ms": int((ended - started) * 1000),
        "summary": (
            f"Collected {len(papers)} papers ({data_source}); "
            f"core={len(core_papers)} supporting={len(supporting_papers)}; "
            f"query={paper_query!r}; rejected={len(rejected_papers)}"
        ),
        "data_source": data_source,
    }
    # Do not write effective_data_mode here — paper||repo run in parallel (LastValue conflict)
    return {
        "papers": papers,
        "subtasks": [rec],
        "mcp_calls": mcp_calls,
        "degradation_events": degradation,
        "events": events
        + [
            _event(
                "paper_finished",
                subtask_id=sub_id,
                ended_at=ended,
                count=len(papers),
                core=len(core_papers),
                supporting=len(supporting_papers),
                rejected=len(rejected_papers),
                source=data_source,
                query=paper_query,
            )
        ],
    }


def repository_analysis_node(state: ResearchState) -> dict[str, Any]:
    """Repository analysis agent — may run in parallel with paper_research."""
    started = time.time()
    sub_id = f"{state['task_id']}-repo"
    work = float(state.get("simulate_work_seconds") or 0.0)
    events = [_event("repo_started", subtask_id=sub_id, started_at=started)]
    _sleep_work(work)

    artifacts_dir = Path(state["artifacts_dir"])
    data_mode = state.get("data_mode") or "fixture"
    question = state["question"]
    repo_query = extract_repo_search_query(question)
    repos: list[dict[str, Any]] = []
    rejected_repos: list[dict[str, Any]] = []
    data_source = "fixture"
    mcp_calls: list[dict[str, Any]] = []
    degradation: list[dict[str, Any]] = []
    resolve_meta: dict[str, Any] = {}

    def _fail_repo(error: str, source: str) -> dict[str, Any]:
        ended = time.time()
        return {
            "repositories": [],
            "subtasks": [
                {
                    "subtask_id": sub_id,
                    "role": "repository_analysis",
                    "status": "failed",
                    "depends_on": [],
                    "started_at": started,
                    "ended_at": ended,
                    "duration_ms": int((ended - started) * 1000),
                    "error": error,
                    "data_source": source,
                }
            ],
            "mcp_calls": mcp_calls,
            "degradation_events": degradation,
            "events": events
            + [
                _event(
                    "repo_failed",
                    error=error,
                    query=repo_query,
                    rejected=len(rejected_repos),
                    resolve_meta=resolve_meta,
                )
            ],
        }

    if data_mode == "live":
        try:
            repo, mcp_calls, resolve_meta = resolve_live_repository(question)
            repos, rejected_repos = filter_relevant_repos(question, [repo])
            data_source = "live_mcp"
            if not repos:
                return _fail_repo(
                    f"live repository resolve found candidates but none passed "
                    f"topic relevance for query={repo_query!r}",
                    "live_mcp",
                )
        except ScholarMcpError as exc:
            if state.get("allow_fixture_fallback"):
                if not fixture_theme_compatible(question, fixture_theme="rag"):
                    return _fail_repo(
                        f"live MCP failed ({exc}); RAG fixture fallback rejected as "
                        f"off-topic for query={repo_query!r}",
                        "fixture_degraded_from_live",
                    )
                raw_fix = load_fixture_repositories(artifacts_dir)
                repos, rejected_repos = filter_relevant_repos(question, raw_fix)
                if not repos:
                    # Fixture is RAG/langchain — accept only when theme-compatible
                    if fixture_theme_compatible(question, fixture_theme="rag"):
                        repos = raw_fix
                        rejected_repos = []
                    else:
                        return _fail_repo(
                            f"live MCP failed ({exc}); fixture repos off-topic "
                            f"for query={repo_query!r}",
                            "fixture_degraded_from_live",
                        )
                data_source = "fixture_degraded_from_live"
                degradation.append(
                    {
                        "ts": time.time(),
                        "node": "repository_analysis",
                        "reason": str(exc),
                        "action": "fixture_fallback_topic_checked",
                        "query": repo_query,
                    }
                )
            else:
                return _fail_repo(f"live MCP failed: {exc}", "live_mcp")
    else:
        if not fixture_theme_compatible(question, fixture_theme="rag"):
            return _fail_repo(
                f"fixture repositories are off-topic for query={repo_query!r}",
                "fixture",
            )
        raw_fix = load_fixture_repositories(artifacts_dir)
        repos, rejected_repos = filter_relevant_repos(question, raw_fix)
        if not repos and fixture_theme_compatible(question, fixture_theme="rag"):
            # Legacy RAG fixture path for vague / RAG-aligned questions
            repos = raw_fix
            rejected_repos = []
        elif not repos:
            return _fail_repo(
                f"fixture repositories failed relevance for query={repo_query!r}",
                "fixture",
            )
        data_source = "fixture"

    ended = time.time()
    rec = {
        "subtask_id": sub_id,
        "role": "repository_analysis",
        "status": "succeeded",
        "depends_on": [],
        "started_at": started,
        "ended_at": ended,
        "duration_ms": int((ended - started) * 1000),
        "summary": (
            f"Collected {len(repos)} repositories ({data_source}); "
            f"query={repo_query!r}; selected={resolve_meta.get('selected')}"
        ),
        "data_source": data_source,
    }
    return {
        "repositories": repos,
        "subtasks": [rec],
        "mcp_calls": mcp_calls,
        "degradation_events": degradation,
        "events": events
        + [
            _event(
                "repo_finished",
                subtask_id=sub_id,
                ended_at=ended,
                count=len(repos),
                rejected=len(rejected_repos),
                source=data_source,
                query=repo_query,
                resolve_meta=resolve_meta,
            )
        ],
    }


def experiment_design_node(state: ResearchState) -> dict[str, Any]:
    """Depends on paper + repository outputs (deterministic template, no LLM required)."""
    started = time.time()
    sub_id = f"{state['task_id']}-experiment"
    papers = state.get("papers") or []
    repos = state.get("repositories") or []
    question = state["question"]
    mode = state.get("workflow_mode") or "research_orchestration"

    # Do not treat failed/empty upstream as usable evidence for full orchestration.
    paper_failed = any(
        s.get("role") == "paper_research" and s.get("status") == "failed"
        for s in state.get("subtasks") or []
    )
    repo_failed = any(
        s.get("role") == "repository_analysis" and s.get("status") == "failed"
        for s in state.get("subtasks") or []
    )
    if mode == "research_orchestration" and (paper_failed or repo_failed or not papers or not repos):
        ended = time.time()
        reasons = []
        if paper_failed or not papers:
            reasons.append("paper_evidence_invalid_or_missing")
        if repo_failed or not repos:
            reasons.append("repository_evidence_invalid_or_missing")
        return {
            "experiment": {},
            "subtasks": [
                {
                    "subtask_id": sub_id,
                    "role": "experiment_design",
                    "status": "failed",
                    "depends_on": ["paper_research", "repository_analysis"],
                    "started_at": started,
                    "ended_at": ended,
                    "duration_ms": int((ended - started) * 1000),
                    "error": "Upstream evidence invalid: " + ", ".join(reasons),
                    "data_source": "none",
                }
            ],
            "events": [_event("experiment_failed", reason=";".join(reasons))],
        }

    if not papers and not repos:
        ended = time.time()
        return {
            "experiment": {},
            "subtasks": [
                {
                    "subtask_id": sub_id,
                    "role": "experiment_design",
                    "status": "failed",
                    "depends_on": ["paper_research", "repository_analysis"],
                    "started_at": started,
                    "ended_at": ended,
                    "duration_ms": int((ended - started) * 1000),
                    "error": "Missing upstream papers and repositories",
                    "data_source": "none",
                }
            ],
            "events": [_event("experiment_failed", reason="missing_upstream")],
        }

    core_papers, supporting_papers = papers_by_tier(papers)
    # Legacy / non-CS: treat untagged accepted papers as core.
    if not core_papers and not requires_core_paper_evidence(question):
        core_papers = [p for p in papers if p.get("relevance_tier") != "supporting"]
    if requires_core_paper_evidence(question) and not core_papers:
        ended = time.time()
        return {
            "experiment": {},
            "subtasks": [
                {
                    "subtask_id": sub_id,
                    "role": "experiment_design",
                    "status": "failed",
                    "depends_on": ["paper_research", "repository_analysis"],
                    "started_at": started,
                    "ended_at": ended,
                    "duration_ms": int((ended - started) * 1000),
                    "error": "Insufficient core paper evidence for experiment design",
                    "data_source": "none",
                }
            ],
            "events": [_event("experiment_failed", reason="insufficient_core_papers")],
        }

    paper_titles = [p.get("title") or p.get("evidence_id") for p in core_papers[:3]]
    supporting_titles = [
        p.get("title") or p.get("evidence_id") for p in supporting_papers[:3]
    ]
    repo_names = [r.get("repository") or r.get("evidence_id") for r in repos[:3]]
    topic = extract_paper_query(question)
    datasets: list[str] = []
    for p in core_papers[:3]:
        for d in p.get("datasets") or []:
            if d and str(d) not in datasets:
                datasets.append(str(d))
    metrics: list[str] = []
    for p in core_papers:
        for m in p.get("metrics") or []:
            if m and str(m) not in metrics:
                metrics.append(str(m))
    # Core evidence drives the plan; supporting is background-only.
    # Never emit fixed RAG / BM25 / NQ / SQuAD templates for non-RAG topics.
    cs_topic = is_compressed_sensing_topic(question)
    if cs_topic:
        default_datasets = [
            "Set11 / BSD68-style natural image CS benchmarks (from core literature)",
            "Declare train/val/test split and sampling ratios (e.g. 10%/25%/40% MR)",
        ]
        default_metrics = [
            "PSNR",
            "SSIM",
            "parameter count",
            "inference time / FLOPs (efficiency)",
        ]
        default_pipeline = [
            f"Problem framing: image compressed sensing reconstruction ({topic})",
            "Select reconstruction networks from CORE papers only",
            f"Prototype / compare using: {', '.join(map(str, repo_names)) or 'CS reconstruction repos'}",
            "Sweep measurement rates; report PSNR/SSIM vs sampling ratio",
            "Ablate network blocks / training losses; document GPU/CPU reproduce steps",
        ]
        default_ablations = [
            "measurement rate sweep",
            "with/without key network module from top CORE paper",
            "loss / training schedule ablation",
        ]
        default_hypotheses = [
            f"Deep CS reconstruction from CORE literature improves PSNR/SSIM vs classical CS baselines for: {topic}",
            f"Open implementation ({', '.join(map(str, repo_names)) or 'n/a'}) can reproduce reported trends under matched sampling rates",
        ]
    else:
        default_datasets = [f"domain datasets for {topic} (to be selected from literature)"]
        default_metrics = ["task-specific metrics from core papers", "reproducibility checklist"]
        default_pipeline = [
            f"Problem framing for: {topic}",
            "Select methods from CORE paper evidence only",
            f"Prototype using: {', '.join(map(str, repo_names)) or 'to-be-selected repos'}",
            "Controlled comparison against literature baselines",
            "Document limitations and reproducibility gaps",
        ]
        default_ablations = [
            "with / without key module from top core paper",
            "alternate baseline from second core paper"
            if len(core_papers) > 1
            else "single-method sanity check",
        ]
        default_hypotheses = [
            f"Methods grounded in CORE evidence improve outcomes for: {topic}",
            f"Open-source references ({', '.join(map(str, repo_names)) or 'n/a'}) "
            f"can support a reproducible baseline for: {topic}",
        ]

    experiment = {
        "objective": question,
        "hypotheses": default_hypotheses,
        "datasets": datasets or default_datasets,
        "baselines": [
            f"Literature baseline from CORE: {paper_titles[0]}" if paper_titles else "Literature baseline",
            "Classical / simplified reconstruction baseline (matched sampling rate)"
            if cs_topic
            else "Ablation / simplified variant of the proposed pipeline",
        ],
        "proposed_pipeline": default_pipeline,
        "evaluation_metrics": metrics[:6] or default_metrics,
        "ablation_studies": default_ablations,
        "resource_requirements": [
            "GPU recommended for deep CS training; CPU possible for inference smoke tests"
            if cs_topic
            else "Depends on core repositories and datasets",
            "optional live MCP for fresher evidence",
        ],
        "implementation_steps": [
            f"Reproduce findings from CORE papers: {', '.join(map(str, paper_titles)) or 'n/a'}",
            f"Reference implementations: {', '.join(map(str, repo_names)) or 'n/a'}",
            "Run controlled comparisons on declared datasets/metrics",
            "Do NOT claim experimental results until actually executed",
        ],
        "risks": [
            "Core evidence may still be incomplete (abstract-only)",
            "External API rate limits for live mode",
            (
                "Supporting (non-core) background only — not primary design basis: "
                + ", ".join(map(str, supporting_titles))
                if supporting_titles
                else "No supporting-only papers retained"
            ),
            "Evidence gaps: need more image-CS CORE papers if list is thin"
            if cs_topic and len(core_papers) < 2
            else "Verify sampling rates / datasets match CORE papers",
        ],
        "upstream_paper_ids": [p.get("evidence_id") for p in core_papers],
        "upstream_supporting_paper_ids": [p.get("evidence_id") for p in supporting_papers],
        "upstream_repo_ids": [r.get("evidence_id") for r in repos],
    }

    ended = time.time()
    return {
        "experiment": experiment,
        "subtasks": [
            {
                "subtask_id": sub_id,
                "role": "experiment_design",
                "status": "succeeded",
                "depends_on": ["paper_research", "repository_analysis"],
                "started_at": started,
                "ended_at": ended,
                "duration_ms": int((ended - started) * 1000),
                "summary": "Built experiment plan from upstream evidence",
                "data_source": "deterministic",
            }
        ],
        "events": [_event("experiment_done", paper_n=len(papers), repo_n=len(repos))],
    }


def review_node(state: ResearchState) -> dict[str, Any]:
    """Deterministic evidence/schema review — not an independent LLM reviewer."""
    started = time.time()
    sub_id = f"{state['task_id']}-review"
    question = state["question"]
    papers = state.get("papers") or []
    repos = state.get("repositories") or []
    experiment = state.get("experiment") or {}
    reviews: list[dict[str, Any]] = []
    decision = "pass"
    errors: list[str] = []

    if state.get("force_fail_review"):
        decision = "fail"
        errors.append("Forced review failure (test hook)")

    mode = state.get("workflow_mode") or "research_orchestration"
    paper_failed = any(
        s.get("role") == "paper_research" and s.get("status") == "failed"
        for s in state.get("subtasks") or []
    )
    repo_failed = any(
        s.get("role") == "repository_analysis" and s.get("status") == "failed"
        for s in state.get("subtasks") or []
    )
    exp_failed = any(
        s.get("role") == "experiment_design" and s.get("status") == "failed"
        for s in state.get("subtasks") or []
    )

    if not papers:
        if mode == "repository_analysis":
            if decision == "pass":
                decision = "needs_supplement"
            errors.append("No paper evidence (repo-only stream)")
        else:
            decision = "fail"
            errors.append("No paper evidence")
    else:
        missing_url = [p.get("evidence_id") for p in papers if not (p.get("source_url") or "").strip()]
        if missing_url:
            decision = "needs_supplement" if decision == "pass" else decision
            reviews.append(
                {
                    "claim": "All papers must include source_url",
                    "related_evidence_ids": missing_url,
                    "status": "unsupported",
                    "reason": "Missing source_url on some papers",
                    "recommended_action": "Re-fetch papers with absolute URLs",
                }
            )

    if not repos:
        if mode == "paper_research":
            if decision == "pass":
                decision = "needs_supplement"
            errors.append("No repository evidence (paper-only stream)")
        else:
            if decision == "pass":
                decision = "needs_supplement"
            errors.append("No repository evidence")

    if paper_failed or repo_failed or exp_failed or not experiment:
        decision = "fail"
        if paper_failed:
            errors.append("paper_research failed — evidence not trustworthy")
        if repo_failed:
            errors.append("repository_analysis failed — evidence not trustworthy")
        if exp_failed or not experiment:
            errors.append("Empty or failed experiment plan")

    core_papers, supporting_papers = papers_by_tier(papers)
    if requires_core_paper_evidence(question) and papers and not core_papers:
        decision = "fail"
        errors.append("No core-tier papers; cannot support research conclusions")

    # Experiment must not treat supporting/irrelevant as core upstream.
    if experiment and requires_core_paper_evidence(question):
        up = set(experiment.get("upstream_paper_ids") or [])
        core_ids = {p.get("evidence_id") for p in core_papers}
        if up - core_ids:
            decision = "fail"
            errors.append(
                "Experiment upstream_paper_ids include non-core evidence: "
                + ", ".join(sorted(str(x) for x in (up - core_ids)))
            )

    # Claims are derived from the current question + evidence ids / tiers only.
    claim_inputs = claims_from_question_and_evidence(question, papers, repos)
    for claim in claim_inputs:
        finding = claim_supported_by_evidence(claim, papers, repos, question)
        reviews.append(finding)
        if finding.get("status") in {"unsupported", "unverified"}:
            if decision == "pass":
                decision = "needs_supplement"
            if finding.get("status") == "unsupported" and mode == "research_orchestration":
                if claim.get("kind") in {
                    "topic_alignment",
                    "repo_alignment",
                    "insufficiency",
                }:
                    decision = "fail"
                    errors.append(f"Claim unsupported: {finding.get('claim')}")

    # Validate via Pydantic when possible
    try:
        ensure_harness_on_path()
        from scholarflow.scholar.models import PaperEvidence, RepositoryEvidence, ExperimentPlan

        for p in strip_relevance_annotations(papers):
            PaperEvidence.model_validate(p)
        for r in strip_relevance_annotations(repos):
            RepositoryEvidence.model_validate(r)
        if experiment:
            ExperimentPlan.model_validate(
                {k: v for k, v in experiment.items() if k in ExperimentPlan.model_fields}
            )
    except Exception as exc:  # noqa: BLE001
        decision = "fail"
        errors.append(f"Schema validation failed: {exc}")
        reviews.append(
            {
                "claim": "Outputs satisfy ScholarFlow schemas",
                "related_evidence_ids": [],
                "status": "unsupported",
                "reason": str(exc),
                "recommended_action": "Fix invalid fields before assemble",
            }
        )

    ended = time.time()
    status = "succeeded" if decision in {"pass", "needs_supplement"} else "failed"
    return {
        "reviews": reviews,
        "review_decision": decision,
        "error": "; ".join(errors) if errors and decision == "fail" else state.get("error"),
        "subtasks": [
            {
                "subtask_id": sub_id,
                "role": "review",
                "status": status,
                "depends_on": ["experiment_design"],
                "started_at": started,
                "ended_at": ended,
                "duration_ms": int((ended - started) * 1000),
                "summary": f"decision={decision}; claims={len(reviews)}",
                "error": "; ".join(errors) if decision == "fail" else None,
                "data_source": "deterministic",
            }
        ],
        "events": [
            _event(
                "review_done",
                decision=decision,
                claim_count=len(reviews),
                reviewer="deterministic_rules",
            )
        ],
    }


def assemble_node(state: ResearchState) -> dict[str, Any]:
    """Aggregate structured artifacts using scholarflow.scholar.artifacts."""
    started = time.time()
    sub_id = f"{state['task_id']}-assemble"
    decision = state.get("review_decision") or "fail"

    if decision == "fail":
        ended = time.time()
        return {
            "overall_status": "failed",
            "artifact_contents": {},
            "artifact_summary": {"artifact_count": 0, "missing": [], "artifacts": []},
            "report_excerpt": None,
            "subtasks": [
                {
                    "subtask_id": sub_id,
                    "role": "assemble",
                    "status": "skipped",
                    "depends_on": ["review"],
                    "started_at": started,
                    "ended_at": ended,
                    "duration_ms": int((ended - started) * 1000),
                    "error": "Skipped because review failed",
                    "data_source": "none",
                }
            ],
            "events": [_event("assemble_skipped")],
        }

    ensure_harness_on_path()
    from scholarflow.scholar.artifacts import build_task_artifacts, summarize_artifacts
    from scholarflow.scholar.models import (
        ExperimentPlan,
        PaperEvidence,
        RepositoryEvidence,
        ResearchPlan,
        ReviewFinding,
    )

    from scholarflow_api.services.artifact_store import persist_artifacts

    plan_dict = state["research_plan"]
    papers_raw = strip_relevance_annotations(state.get("papers") or [])
    repos_raw = strip_relevance_annotations(state.get("repositories") or [])
    exp_raw = state.get("experiment") or {}
    reviews_raw = state.get("reviews") or []
    data_mode = state.get("data_mode") or "fixture"
    mcp_calls: list[dict[str, Any]] = []

    plan = ResearchPlan.model_validate(plan_dict)
    papers = [PaperEvidence.model_validate(p) for p in papers_raw]
    repos = [RepositoryEvidence.model_validate(r) for r in repos_raw]
    experiment = ExperimentPlan.model_validate(
        {k: v for k, v in exp_raw.items() if k in ExperimentPlan.model_fields}
    )
    reviews = [ReviewFinding.model_validate(r) for r in reviews_raw]

    assemble_source = "local_artifacts"
    degradation: list[dict[str, Any]] = []
    try:
        if data_mode == "live":
            assembled, assemble_calls = assemble_via_mcp(
                plan.model_dump(),
                [p.model_dump() for p in papers],
                [r.model_dump() for r in repos],
                experiment.model_dump(),
                [rv.model_dump() for rv in reviews],
            )
            mcp_calls.extend(assemble_calls)
            contents = assembled["contents"]
            summary = {
                "artifact_count": assembled.get("artifact_count"),
                "artifacts": assembled.get("artifacts"),
                "missing": assembled.get("missing") or [],
            }
            assemble_source = "live_mcp"
        else:
            contents = build_task_artifacts(plan, papers, repos, experiment, reviews)
            summary = summarize_artifacts(contents)
    except ScholarMcpError as exc:
        # Structural assemble may fall back locally, but must be marked (never silent live success)
        contents = build_task_artifacts(plan, papers, repos, experiment, reviews)
        summary = summarize_artifacts(contents)
        assemble_source = "local_after_mcp_assemble_error"
        degradation.append(
            {
                "ts": time.time(),
                "node": "assemble",
                "reason": str(exc),
                "action": "local_assemble_fallback",
            }
        )

    report = contents.get("research_report.md", "")
    excerpt = report[:1200]

    manifest: dict[str, Any] | None = None
    if state.get("persist_artifacts", True):
        refs = [p.evidence_id for p in papers] + [r.evidence_id for r in repos]
        eff_mode = state.get("effective_data_mode") or data_mode
        if state.get("degradation_events"):
            eff_mode = "mixed_degraded"
        man = persist_artifacts(
            state["task_id"],
            contents,
            data_mode=eff_mode,
            evidence_refs=refs,
            overwrite=True,
        )
        manifest = man.model_dump()

    paper_ok = any(
        s.get("role") == "paper_research" and s.get("status") == "succeeded"
        for s in state.get("subtasks") or []
    )
    repo_ok = any(
        s.get("role") == "repository_analysis" and s.get("status") == "succeeded"
        for s in state.get("subtasks") or []
    )
    degraded = bool(state.get("degradation_events")) or bool(degradation)
    if decision == "needs_supplement" or not (paper_ok and repo_ok) or degraded:
        overall = "partial_succeeded"
    else:
        overall = "succeeded"

    ended = time.time()
    return {
        "artifact_contents": contents,
        "artifact_summary": summary,
        "artifact_manifest": manifest,
        "report_excerpt": excerpt,
        "overall_status": overall,
        "degradation_events": degradation,
        "effective_data_mode": (
            "mixed_degraded" if degraded else (state.get("effective_data_mode") or data_mode)
        ),
        "mcp_calls": mcp_calls,
        "subtasks": [
            {
                "subtask_id": sub_id,
                "role": "assemble",
                "status": "succeeded",
                "depends_on": ["review"],
                "started_at": started,
                "ended_at": ended,
                "duration_ms": int((ended - started) * 1000),
                "summary": f"Built {summary.get('artifact_count')} artifacts ({assemble_source})",
                "data_source": assemble_source,
            }
        ],
        "events": [
            _event(
                "assemble_done",
                overall=overall,
                count=summary.get("artifact_count"),
                persisted=bool(manifest),
                source=assemble_source,
            )
        ],
    }
