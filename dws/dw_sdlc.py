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
DW SDLC - Full software development lifecycle pipeline.

Plan → Build → Test → Review (+patch loop) → Security Review (+patch loop)

Usage:
    ./dws/dw_sdlc.py "Add input validation to apps/main.py"
    ./dws/dw_sdlc.py "Add error handling" --model gpt-4o
    ./dws/dw_sdlc.py "Add logging" --max-patch-iterations 2
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

MAX_PATCH_ITERATIONS = 3


def review_needs_patch(review_output: str, review_type: str) -> bool:
    """Check if review output indicates issues that need patching."""
    if not review_output:
        return False
    upper = review_output.upper()
    lower = review_output.lower()
    if review_type == "review":
        return "FAIL" in upper or '"blocker"' in lower
    # security_review
    return "FAIL" in upper or '"critical"' in lower or '"high"' in lower


@click.command()
@click.argument("prompt", required=True)
@click.option("--model", type=str, default=None, help="Model to use")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory (default: current directory)",
)
@click.option(
    "--max-patch-iterations",
    type=int,
    default=MAX_PATCH_ITERATIONS,
    help=f"Max patch loop iterations per review (default: {MAX_PATCH_ITERATIONS})",
)
@click.option(
    "--dw-id", type=str, default=None, help="DW ID (auto-generated if omitted)"
)
def main(
    prompt: str, model: str, working_dir: str, max_patch_iterations: int, dw_id: str
):
    """Run full SDLC pipeline: Plan → Build → Test → Review(+Patch) → Security(+Patch)."""
    console = Console()
    if not dw_id:
        dw_id = generate_short_id()

    if not working_dir:
        working_dir = os.getcwd()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    console.print(
        Panel(
            f"[bold blue]Full SDLC Pipeline[/bold blue]\n\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Prompt:[/cyan] {prompt}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}\n"
            f"[cyan]Max Patch Iterations:[/cyan] {max_patch_iterations}",
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

    # ── Phase 1: Plan ──
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

    # ── Phase 2: Build ──
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

    # ── Phase 3: Test ──
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
        console.print("[yellow]Test phase failed — continuing to review.[/yellow]\n")

    # ── Phase 4: Review + Patch Loop ──
    run_phase(
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
    )

    state = load_state(dw_id)
    review_output = ""
    if state and "review" in state.phases:
        review_output = state.phases["review"].output or ""

    for iteration in range(1, max_patch_iterations + 1):
        if not review_needs_patch(review_output, "review"):
            console.print("[green]Review passed — no patch needed.[/green]\n")
            break

        console.print(
            Panel(
                f"[yellow]Review found issues. Patch iteration {iteration}/{max_patch_iterations}[/yellow]",
                border_style="yellow",
            )
        )

        # Patch
        patch_name = f"patch_review_{iteration}"
        if not run_phase(
            patch_name,
            [
                "uv",
                "run",
                os.path.join(script_dir, "dw_patch.py"),
                "--dw-id",
                dw_id,
                "--review-phase",
                "review",
                "--iteration",
                str(iteration),
                *model_args,
                *dir_args,
            ],
        ):
            break

        # Re-review
        re_review_name = f"review_{iteration + 1}"
        run_phase(
            re_review_name,
            [
                "uv",
                "run",
                os.path.join(script_dir, "dw_review.py"),
                "--dw-id",
                dw_id,
                *model_args,
                *dir_args,
            ],
        )

        state = load_state(dw_id)
        review_output = ""
        if state and "review" in state.phases:
            review_output = state.phases["review"].output or ""
    else:
        if review_needs_patch(review_output, "review"):
            console.print(
                f"[yellow]Review still has issues after {max_patch_iterations} patches — moving on.[/yellow]\n"
            )

    # ── Phase 5: Security Review + Patch Loop ──
    run_phase(
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
    )

    state = load_state(dw_id)
    sec_output = ""
    if state and "security_review" in state.phases:
        sec_output = state.phases["security_review"].output or ""

    for iteration in range(1, max_patch_iterations + 1):
        if not review_needs_patch(sec_output, "security_review"):
            console.print("[green]Security review passed — no patch needed.[/green]\n")
            break

        console.print(
            Panel(
                f"[yellow]Security review found issues. Patch iteration {iteration}/{max_patch_iterations}[/yellow]",
                border_style="yellow",
            )
        )

        # Patch
        patch_name = f"patch_security_{iteration}"
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
                str(iteration),
                *model_args,
                *dir_args,
            ],
        ):
            break

        # Re-review security
        re_sec_name = f"security_review_{iteration + 1}"
        run_phase(
            re_sec_name,
            [
                "uv",
                "run",
                os.path.join(script_dir, "dw_security_review.py"),
                "--dw-id",
                dw_id,
                *model_args,
                *dir_args,
            ],
        )

        state = load_state(dw_id)
        sec_output = ""
        if state and "security_review" in state.phases:
            sec_output = state.phases["security_review"].output or ""
    else:
        if review_needs_patch(sec_output, "security_review"):
            console.print(
                f"[yellow]Security review still has issues after {max_patch_iterations} patches — moving on.[/yellow]\n"
            )

    # ── Summary ──
    console.print()
    console.print(Rule("[bold blue]SDLC Pipeline Summary[/bold blue]"))

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
                "workflow": "sdlc",
                "dw_id": dw_id,
                "prompt": prompt,
                "model": model,
                "max_patch_iterations": max_patch_iterations,
                "phases": phase_results,
                "overall_success": overall_success,
            },
            f,
            indent=2,
        )

    if overall_success:
        console.print(
            "\n[bold green]SDLC pipeline completed successfully![/bold green]"
        )
    else:
        console.print(
            "\n[bold yellow]SDLC pipeline completed with issues.[/bold yellow]"
        )

    console.print(f"[dim]DW ID: {dw_id}[/dim]")
    console.print(f"[dim]Summary: {summary_path}[/dim]")

    if not overall_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
