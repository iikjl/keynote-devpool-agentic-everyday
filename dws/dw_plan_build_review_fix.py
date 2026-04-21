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
DW Plan Build Review Fix - Composite pipeline with feedback loop.

Chains Plan + Build + Review, and if the review finds blockers,
triggers another Build pass to fix them.

Usage:
    ./dws/dw_plan_build_review_fix.py "Add error handling to apps/main.py"
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

from agent import generate_short_id
from state import load_state

MAX_FIX_ATTEMPTS = 2


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
    """Run Plan + Build + Review + Fix pipeline."""
    console = Console()
    if not dw_id:
        dw_id = generate_short_id()

    if not working_dir:
        working_dir = os.getcwd()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    console.print(
        Panel(
            f"[bold blue]Plan + Build + Review + Fix Pipeline[/bold blue]\n\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Prompt:[/cyan] {prompt}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}\n"
            f"[cyan]Max Fix Attempts:[/cyan] {MAX_FIX_ATTEMPTS}",
            title="[bold blue]Pipeline Configuration[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    phase_results = {}
    model_args = ["--model", model] if model else []
    dir_args = ["--working-dir", working_dir] if working_dir else []

    def run_phase(name, cmd):
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

    # Phase 2: Build
    if not run_phase(
        "build",
        [
            "uv",
            "run",
            os.path.join(script_dir, "dw_build.py"),
            "--dw-id",
            dw_id,
            *model_args,
            *dir_args,
        ],
    ):
        sys.exit(1)

    # Phase 3: Review
    if not run_phase(
        "review",
        [
            "uv",
            "run",
            os.path.join(script_dir, "dw_review.py"),
            "--dw-id",
            dw_id,
            *model_args,
            *dir_args,
        ],
    ):
        # Review failed to run — but we still check the output
        console.print("[yellow]Review phase had issues, checking output...[/yellow]")

    # Check review output for blockers
    state = load_state(dw_id)
    review_output = ""
    if state and "review" in state.phases:
        review_output = state.phases["review"].output

    needs_fix = "FAIL" in review_output.upper() or '"blocker"' in review_output.lower()

    # Phase 4: Fix loop (if review found blockers)
    fix_attempt = 0
    while needs_fix and fix_attempt < MAX_FIX_ATTEMPTS:
        fix_attempt += 1
        fix_name = f"fix_{fix_attempt}"

        console.print(
            Panel(
                f"[yellow]Review found issues. Running fix attempt {fix_attempt}/{MAX_FIX_ATTEMPTS}[/yellow]",
                border_style="yellow",
            )
        )

        # Re-run build (the builder will see the current state of files + review feedback)
        if not run_phase(
            fix_name,
            [
                "uv",
                "run",
                os.path.join(script_dir, "dw_build.py"),
                "--dw-id",
                dw_id,
                *model_args,
                *dir_args,
            ],
        ):
            break

        # Re-run review
        review_name = f"review_{fix_attempt + 1}"
        if not run_phase(
            review_name,
            [
                "uv",
                "run",
                os.path.join(script_dir, "dw_review.py"),
                "--dw-id",
                dw_id,
                *model_args,
                *dir_args,
            ],
        ):
            break

        # Re-check
        state = load_state(dw_id)
        if state and review_name in state.phases:
            review_output = state.phases[review_name].output
            needs_fix = (
                "FAIL" in review_output.upper() or '"blocker"' in review_output.lower()
            )
        else:
            needs_fix = False

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

    # Save workflow summary
    project_root = os.path.dirname(script_dir)
    summary_path = os.path.join(project_root, "agents", dw_id, "workflow_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(
            {
                "workflow": "plan_build_review_fix",
                "dw_id": dw_id,
                "prompt": prompt,
                "model": model,
                "phases": phase_results,
                "fix_attempts": fix_attempt,
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
