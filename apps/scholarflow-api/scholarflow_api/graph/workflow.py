"""Build and run ScholarFlow LangGraph research workflows."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from scholarflow_api.graph.nodes import (
    assemble_node,
    experiment_design_node,
    orchestrator_node,
    paper_research_node,
    repository_analysis_node,
    review_node,
)
from scholarflow_api.graph.state import ResearchState, WorkflowMode

logger = logging.getLogger("scholarflow_api.graph.workflow")


def _route_after_orchestrator(state: ResearchState) -> list[str]:
    """Fan-out: paper & repo in parallel for orchestration; single path otherwise."""
    mode = state.get("workflow_mode") or "research_orchestration"
    if mode == "paper_research":
        return ["paper_research"]
    if mode == "repository_analysis":
        return ["repository_analysis"]
    if mode == "experiment_design":
        # Still need upstream evidence — run paper+repo first then experiment via join
        return ["paper_research", "repository_analysis"]
    # research_orchestration
    return ["paper_research", "repository_analysis"]


def _after_paper(state: ResearchState) -> str:
    mode = state.get("workflow_mode") or "research_orchestration"
    if mode == "paper_research":
        return "review_direct"
    return "join_gate"


def _after_repo(state: ResearchState) -> str:
    mode = state.get("workflow_mode") or "research_orchestration"
    if mode == "repository_analysis":
        return "review_direct"
    return "join_gate"


def join_gate_node(state: ResearchState) -> dict[str, Any]:
    """Synchronization barrier after parallel paper/repo (no-op payload)."""
    return {
        "events": [{"ts": __import__("time").time(), "kind": "join_gate", "task_id": state["task_id"]}]
    }


def review_direct_prepare(state: ResearchState) -> dict[str, Any]:
    """For single-stream modes, synthesize minimal experiment if missing."""
    mode = state.get("workflow_mode") or "research_orchestration"
    updates: dict[str, Any] = {}
    if mode == "paper_research" and not state.get("repositories"):
        updates["repositories"] = []
    if mode == "repository_analysis" and not state.get("papers"):
        updates["papers"] = []
    if mode in {"paper_research", "repository_analysis"} and not state.get("experiment"):
        # Minimal experiment so review/assemble can still produce artifacts
        updates["experiment"] = {
            "objective": state["question"],
            "hypotheses": ["Single-stream workflow placeholder hypothesis"],
            "datasets": [],
            "baselines": ["Literature baseline from collected evidence"],
            "proposed_pipeline": ["Inspect collected evidence", "Draft follow-up plan"],
            "evaluation_metrics": ["evidence coverage", "source_url completeness"],
            "ablation_studies": [],
            "resource_requirements": [],
            "implementation_steps": ["Use collected evidence"],
            "risks": ["Incomplete dual-evidence for experiment-only claims"],
        }
    return updates


def build_research_graph() -> Any:
    """Compile the ScholarFlow research StateGraph."""
    g: StateGraph = StateGraph(ResearchState)

    g.add_node("orchestrator", orchestrator_node)
    g.add_node("paper_research", paper_research_node)
    g.add_node("repository_analysis", repository_analysis_node)
    g.add_node("join_gate", join_gate_node)
    g.add_node("experiment_design", experiment_design_node)
    g.add_node("review_direct", review_direct_prepare)
    g.add_node("review", review_node)
    g.add_node("assemble", assemble_node)

    g.add_edge(START, "orchestrator")
    g.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        ["paper_research", "repository_analysis"],
    )

    # Paper branch
    g.add_conditional_edges(
        "paper_research",
        _after_paper,
        {"join_gate": "join_gate", "review_direct": "review_direct"},
    )
    # Repo branch
    g.add_conditional_edges(
        "repository_analysis",
        _after_repo,
        {"join_gate": "join_gate", "review_direct": "review_direct"},
    )

    # Parallel join -> experiment -> review -> assemble
    g.add_edge("join_gate", "experiment_design")
    g.add_edge("experiment_design", "review")

    # Single-stream path: prepare minimal experiment then review
    g.add_edge("review_direct", "review")

    g.add_edge("review", "assemble")
    g.add_edge("assemble", END)

    return g.compile()


@lru_cache
def get_compiled_graph() -> Any:
    return build_research_graph()


def run_research_workflow(
    *,
    task_id: str,
    question: str,
    workflow_mode: WorkflowMode = "research_orchestration",
    artifacts_dir: str,
    data_mode: Literal["fixture", "live"] = "fixture",
    allow_fixture_fallback: bool = False,
    force_fail_review: bool = False,
    force_fail_paper: bool = False,
    simulate_work_seconds: float = 0.0,
    persist_artifacts: bool = True,
) -> ResearchState:
    """Execute the compiled graph and return final state."""
    graph = get_compiled_graph()
    initial: ResearchState = {
        "task_id": task_id,
        "question": question,
        "workflow_mode": workflow_mode,
        "data_mode": data_mode,
        "allow_fixture_fallback": allow_fixture_fallback,
        "force_fail_review": force_fail_review,
        "force_fail_paper": force_fail_paper,
        "simulate_work_seconds": simulate_work_seconds,
        "artifacts_dir": artifacts_dir,
        "persist_artifacts": persist_artifacts,
        "papers": [],
        "repositories": [],
        "reviews": [],
        "subtasks": [],
        "events": [],
        "mcp_calls": [],
        "degradation_events": [],
        "overall_status": "failed",
        "error": None,
        "effective_data_mode": data_mode,
    }
    logger.info(
        "invoke research graph task=%s mode=%s data_mode=%s",
        task_id,
        workflow_mode,
        data_mode,
    )
    final = graph.invoke(initial)
    return final  # type: ignore[return-value]
