from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_workflows_use_an_existing_setup_uv_major_version() -> None:
    workflows = sorted((REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml"))

    setup_steps = [
        step
        for workflow in workflows
        for job in yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step, dict) and str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]

    assert setup_steps
    assert {step["uses"] for step in setup_steps} == {"astral-sh/setup-uv@v7"}
