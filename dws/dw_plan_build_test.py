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
DW Plan Build Test - Composite pipeline: Plan + Build + Test.

Chains planning, build, and test phases via subprocess.

Usage:
    ./dws/dw_plan_build_test.py "Add input validation to apps/main.py"
    ./dws/dw_plan_build_test.py "Add logging" --model gpt-4o
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


@click.command()
@click.argument("prompt", required=True)
@click.option("--model", type=str, default=None, help="Model to use")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory (default: current directory)",
)
def main(prompt: str, model: str, working_dir: str):
    """Run Plan + Build + Test pipeline."""
    console = Console()
    dw_id = generate_short_id()

    if not working_dir:
        working_dir = os.getcwd()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    console.print(
        Panel(
            f"[bold blue]Plan + Build + Test Pipeline[/bold blue]\n\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Prompt:[/cyan] {prompt}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}",
            title="[bold blue]Pipeline Configuration[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    phase_results = {}

    def run_phase(name, cmd):
        console.print(Rule(f"[bold yellow]Phase: {name.title()}[/bold yellow]"))
        console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            phase_results[name] = "failed"
            console.print(
                f"\n[bold red]{name.title()} phase failed. Pipeline aborted.[/bold red]"
            )
            return False
        phase_results[name] = "success"
        console.print()
        return True

    # Common args
    model_args = ["--model", model] if model else []
    dir_args = ["--working-dir", working_dir] if working_dir else []

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

    # Phase 3: Test
    if not run_phase(
        "test",
        [
            "uv",
            "run",
            os.path.join(script_dir, "dw_test.py"),
            "--dw-id",
            dw_id,
            *model_args,
            *dir_args,
        ],
    ):
        sys.exit(1)

    # Summary
    console.print(Rule("[bold blue]Pipeline Summary[/bold blue]"))

    summary_table = Table(show_header=True, box=None)
    summary_table.add_column("Phase", style="bold cyan")
    summary_table.add_column("Status", style="bold")
    for phase, status in phase_results.items():
        color = "green" if status == "success" else "red"
        summary_table.add_row(phase.title(), f"[{color}]{status.title()}[/{color}]")
    console.print(summary_table)

    # Save workflow summary
    project_root = os.path.dirname(script_dir)
    summary_path = os.path.join(project_root, "agents", dw_id, "workflow_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(
            {
                "workflow": "plan_build_test",
                "dw_id": dw_id,
                "prompt": prompt,
                "model": model,
                "phases": phase_results,
                "overall_success": all(s == "success" for s in phase_results.values()),
            },
            f,
            indent=2,
        )

    console.print("\n[bold green]Pipeline completed successfully![/bold green]")
    console.print(f"[dim]DW ID: {dw_id}[/dim]")
    console.print(f"[dim]Summary: {summary_path}[/dim]")


if __name__ == "__main__":
    main()
