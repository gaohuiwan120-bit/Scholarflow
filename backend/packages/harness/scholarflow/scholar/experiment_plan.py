"""Render ExperimentPlan as Markdown."""

from __future__ import annotations

from scholarflow.scholar.models import ExperimentPlan


def render_experiment_plan_md(plan: ExperimentPlan) -> str:
    sections = [
        "# Experiment Plan\n",
        "## Objective\n",
        plan.objective + "\n",
        "## Hypotheses\n",
        _bullets(plan.hypotheses),
        "## Datasets\n",
        _bullets(plan.datasets),
        "## Baselines\n",
        _bullets(plan.baselines),
        "## Proposed Pipeline\n",
        _bullets(plan.proposed_pipeline),
        "## Evaluation Metrics\n",
        _bullets(plan.evaluation_metrics),
        "## Ablation Studies\n",
        _bullets(plan.ablation_studies),
        "## Resource Requirements\n",
        _bullets(plan.resource_requirements),
        "## Implementation Steps\n",
        _bullets(plan.implementation_steps),
        "## Risks\n",
        _bullets(plan.risks),
    ]
    return "".join(sections)


def _bullets(items: list[str]) -> str:
    if not items:
        return "- (none)\n"
    return "".join(f"- {item}\n" for item in items)
