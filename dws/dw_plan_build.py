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
DW Plan Build - Composite pipeline: Plan + Build.

Chains the planning and build phases via subprocess.

Usage:
    ./dws/dw_plan_build.py "Add a health check endpoint to apps/main.py"
    ./dws/dw_plan_build.py "Refactor error handling" --model gpt-4o
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
    """Run Plan + Build pipeline."""
    console = Console()
    dw_id = generate_short_id()

    if not working_dir:
        working_dir = os.getcwd()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    console.print(
        Panel(
            f"[bold blue]Plan + Build Pipeline[/bold blue]\n\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Prompt:[/cyan] {prompt}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}",
            title="[bold blue]Pipeline Configuration[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    # Phase 1: Plan
    console.print(Rule("[bold yellow]Phase 1: Plan[/bold yellow]"))
    plan_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "dw_plan.py"),
        prompt,
        "--dw-id",
        dw_id,
    ]
    if model:
        plan_cmd.extend(["--model", model])
    if working_dir:
        plan_cmd.extend(["--working-dir", working_dir])

    console.print(f"[dim]Running: {' '.join(plan_cmd)}[/dim]\n")
    result = subprocess.run(plan_cmd)
    if result.returncode != 0:
        console.print("\n[bold red]Plan phase failed. Pipeline aborted.[/bold red]")
        sys.exit(1)

    # Phase 2: Build
    console.print()
    console.print(Rule("[bold yellow]Phase 2: Build[/bold yellow]"))
    build_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "dw_build.py"),
        "--dw-id",
        dw_id,
    ]
    if model:
        build_cmd.extend(["--model", model])
    if working_dir:
        build_cmd.extend(["--working-dir", working_dir])

    console.print(f"[dim]Running: {' '.join(build_cmd)}[/dim]\n")
    result = subprocess.run(build_cmd)
    if result.returncode != 0:
        console.print("\n[bold red]Build phase failed.[/bold red]")
        sys.exit(1)

    # Summary
    console.print()
    console.print(Rule("[bold blue]Pipeline Summary[/bold blue]"))

    summary_table = Table(show_header=True, box=None)
    summary_table.add_column("Phase", style="bold cyan")
    summary_table.add_column("Status", style="bold")
    summary_table.add_row("Plan", "[green]Success[/green]")
    summary_table.add_row("Build", "[green]Success[/green]")
    console.print(summary_table)

    # Save workflow summary
    project_root = os.path.dirname(script_dir)
    summary_path = os.path.join(project_root, "agents", dw_id, "workflow_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(
            {
                "workflow": "plan_build",
                "dw_id": dw_id,
                "prompt": prompt,
                "model": model,
                "phases": ["plan", "build"],
                "overall_success": True,
            },
            f,
            indent=2,
        )

    console.print("\n[bold green]Pipeline completed successfully![/bold green]")
    console.print(f"[dim]DW ID: {dw_id}[/dim]")
    console.print(f"[dim]Summary: {summary_path}[/dim]")


if __name__ == "__main__":
    main()
