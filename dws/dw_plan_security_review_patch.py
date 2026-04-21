#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic",
#   "python-dotenv",
#   "click",
#   "rich",
# ]
# ///
"""
DW Plan Security Review Patch - Security-first composite pipeline.

Chains Plan + Security Review, and if the security review flags findings,
loops Patch + Security Review until clean or max iterations reached.

Intended as the default workflow for the PR trigger so that a PR review
produces a plan, an OWASP-graded audit, and (if needed) targeted patches.

Usage:
    ./dws/dw_plan_security_review_patch.py "Review this PR for OWASP Top 10"
    ./dws/dw_plan_security_review_patch.py "..." --dw-id abc12345
"""

import json
import os
import subprocess
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dw_modules"))

from agent import generate_short_id  # noqa: E402
from state import load_state  # noqa: E402

MAX_FIX_ATTEMPTS = 2


def needs_patch(output: str) -> bool:
    """Heuristic: did the security review surface anything actionable?"""
    if not output:
        return False
    upper = output.upper()
    if "FAIL" in upper or "CRITICAL" in upper or "HIGH" in upper:
        return True
    lower = output.lower()
    if '"blocker"' in lower or '"severity": "high"' in lower:
        return True
    return False


@click.command()
@click.argument("prompt", required=True)
@click.option(
    "--dw-id",
    type=str,
    default=None,
    help="DW ID (auto-generated if omitted)",
)
@click.option("--model", type=str, default=None, help="Model to use")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory (default: current directory)",
)
def main(prompt: str, dw_id: str, model: str, working_dir: str):
    """Run Plan + Security Review + Patch-loop pipeline."""
    console = Console()
    if not dw_id:
        dw_id = generate_short_id()

    if not working_dir:
        working_dir = os.getcwd()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    preview = prompt if len(prompt) <= 160 else prompt[:160] + "..."
    console.print(
        Panel(
            f"[bold blue]Plan + Security Review + Patch Pipeline[/bold blue]\n\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Prompt preview:[/cyan] {preview}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}\n"
            f"[cyan]Max Patch Attempts:[/cyan] {MAX_FIX_ATTEMPTS}",
            title="[bold blue]Pipeline Configuration[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    phase_results: dict[str, str] = {}
    model_args = ["--model", model] if model else []
    dir_args = ["--working-dir", working_dir] if working_dir else []

    def run_phase(name: str, cmd: list[str]) -> bool:
        console.print(Rule(f"[bold yellow]Phase: {name}[/bold yellow]"))
        console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            phase_results[name] = "failed"
            console.print(f"\n[bold red]{name} phase failed.[/bold red]")
            return False
        phase_results[name] = "success"
        console.print()
        return True

    # Phase 1: Plan
    if not run_phase(
        "plan",
        [
            "uv",
            "run",
            os.path.join(script_dir, "dw_plan.py"),
            prompt,
            "--dw-id",
            dw_id,
            *model_args,
            *dir_args,
        ],
    ):
        sys.exit(1)

    # Phase 2: Security Review
    if not run_phase(
        "security_review",
        [
            "uv",
            "run",
            os.path.join(script_dir, "dw_security_review.py"),
            "--dw-id",
            dw_id,
            *model_args,
            *dir_args,
        ],
    ):
        console.print(
            "[yellow]Security review phase had issues, checking output...[/yellow]"
        )

    state = load_state(dw_id)
    review_output = ""
    if state and "security_review" in state.phases:
        review_output = state.phases["security_review"].output

    # Phase 3: Patch loop (up to MAX_FIX_ATTEMPTS)
    patch_attempt = 0
    while needs_patch(review_output) and patch_attempt < MAX_FIX_ATTEMPTS:
        patch_attempt += 1
        patch_name = f"patch_{patch_attempt}"

        console.print(
            Panel(
                f"[yellow]Security review found findings. "
                f"Running patch attempt {patch_attempt}/{MAX_FIX_ATTEMPTS}[/yellow]",
                border_style="yellow",
            )
        )

        if not run_phase(
            patch_name,
            [
                "uv",
                "run",
                os.path.join(script_dir, "dw_patch.py"),
                "--dw-id",
                dw_id,
                "--review-phase",
                "security_review",
                "--iteration",
                str(patch_attempt),
                *model_args,
                *dir_args,
            ],
        ):
            break

        # Re-run security review; dw_security_review writes to the same
        # phase key so we re-read from state["security_review"].
        reverify_name = f"security_review_{patch_attempt + 1}"
        if not run_phase(
            reverify_name,
            [
                "uv",
                "run",
                os.path.join(script_dir, "dw_security_review.py"),
                "--dw-id",
                dw_id,
                *model_args,
                *dir_args,
            ],
        ):
            break

        state = load_state(dw_id)
        if state and "security_review" in state.phases:
            review_output = state.phases["security_review"].output
        else:
            break

    # Summary
    console.print()
    console.print(Rule("[bold blue]Pipeline Summary[/bold blue]"))

    summary_table = Table(show_header=True, box=None)
    summary_table.add_column("Phase", style="bold cyan")
    summary_table.add_column("Status", style="bold")
    for phase, status in phase_results.items():
        color = "green" if status == "success" else "red"
        summary_table.add_row(phase, f"[{color}]{status.title()}[/{color}]")
    console.print(summary_table)

    overall_success = all(s == "success" for s in phase_results.values())

    project_root = os.path.dirname(script_dir)
    summary_path = os.path.join(project_root, "agents", dw_id, "workflow_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(
            {
                "workflow": "plan_security_review_patch",
                "dw_id": dw_id,
                "prompt": prompt,
                "model": model,
                "phases": phase_results,
                "patch_attempts": patch_attempt,
                "overall_success": overall_success,
            },
            f,
            indent=2,
        )

    if overall_success:
        console.print("\n[bold green]Pipeline completed successfully![/bold green]")
    else:
        console.print("\n[bold yellow]Pipeline completed with issues.[/bold yellow]")

    console.print(f"[dim]DW ID: {dw_id}[/dim]")
    console.print(f"[dim]Summary: {summary_path}[/dim]")

    if not overall_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
