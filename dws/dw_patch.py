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
DW Patch - Fix issues found by review or security review.

Reads review output from state and applies targeted fixes.

Usage:
    ./dws/dw_patch.py --dw-id abc12345 --review-phase review
    ./dws/dw_patch.py --dw-id abc12345 --review-phase security_review
"""

import os
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dw_modules"))

from agent import (
    FINAL_OBJECT_JSON,
    OUTPUT_JSON,
    OUTPUT_JSONL,
    CopilotPromptRequest,
    prompt_copilot_with_retry,
)
from state import load_state, update_phase
from template_loader import load_and_render


@click.command()
@click.option("--dw-id", type=str, required=True, help="DW ID from planning phase")
@click.option(
    "--review-phase",
    type=str,
    required=True,
    help="Name of the review phase to patch (e.g. 'review', 'security_review')",
)
@click.option("--iteration", type=int, default=1, help="Patch iteration number")
@click.option("--model", type=str, default=None, help="Model to use")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory (default: from state)",
)
def main(dw_id: str, review_phase: str, iteration: int, model: str, working_dir: str):
    """Fix issues found by a review phase."""
    console = Console()
    agent_name = f"patcher_{review_phase}_{iteration}"

    # Load state
    state = load_state(dw_id)
    if not state:
        console.print(f"[red]No state found for DW ID: {dw_id}[/red]")
        sys.exit(1)

    if not state.plan_file:
        console.print(f"[red]No plan file in state for DW ID: {dw_id}[/red]")
        sys.exit(1)

    # Get review output from state
    review_output = ""
    if review_phase in state.phases:
        review_output = state.phases[review_phase].output
    if not review_output:
        console.print(f"[red]No output found for phase '{review_phase}' in state[/red]")
        sys.exit(1)

    if not working_dir:
        working_dir = state.working_dir or os.getcwd()
    if not model:
        model = state.model

    # Display info
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column(style="bold cyan")
    info_table.add_column()
    info_table.add_row("DW ID", dw_id)
    info_table.add_row("Phase", f"Patch ({review_phase} iter {iteration})")
    info_table.add_row("Plan File", state.plan_file)
    info_table.add_row("Fixing", review_phase)
    info_table.add_row("Model", model or "(default)")
    info_table.add_row("Agent", agent_name)

    console.print(
        Panel(
            info_table, title="[bold blue]Patch Phase[/bold blue]", border_style="blue"
        )
    )
    console.print()

    # Render template
    rendered_prompt = load_and_render(
        "patch",
        PLAN_FILE=state.plan_file,
        REVIEW_OUTPUT=review_output,
    )

    # Build request
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "agents", dw_id, agent_name)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, OUTPUT_JSONL)

    request = CopilotPromptRequest(
        prompt=rendered_prompt,
        dw_id=dw_id,
        agent_name=agent_name,
        model=model,
        output_file=output_file,
        working_dir=working_dir,
    )

    # Execute
    phase_key = f"patch_{review_phase}_{iteration}"
    update_phase(state, phase_key, "running", agent_name=agent_name)

    try:
        with console.status("[bold yellow]Patching issues...[/bold yellow]"):
            response = prompt_copilot_with_retry(request)

        if response.success:
            update_phase(
                state,
                phase_key,
                "success",
                agent_name=agent_name,
                output=response.output,
                session_id=response.session_id,
            )
            console.print(
                Panel(
                    response.output,
                    title="[bold green]Patch Success[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
        else:
            update_phase(
                state,
                phase_key,
                "failed",
                agent_name=agent_name,
                output=response.output,
            )
            console.print(
                Panel(
                    response.output,
                    title="[bold red]Patch Failed[/bold red]",
                    border_style="red",
                    padding=(1, 2),
                )
            )
            sys.exit(1)

    except Exception as e:
        update_phase(state, phase_key, "failed", agent_name=agent_name, output=str(e))
        console.print(
            Panel(
                f"[bold red]{e}[/bold red]",
                title="[bold red]Error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(2)

    # Show output files
    files_table = Table(show_header=True, box=None)
    files_table.add_column("File", style="bold cyan")
    files_table.add_column("Path", style="dim")
    files_table.add_row("JSONL Stream", os.path.join(output_dir, OUTPUT_JSONL))
    files_table.add_row("JSON Array", os.path.join(output_dir, OUTPUT_JSON))
    files_table.add_row("Final Object", os.path.join(output_dir, FINAL_OBJECT_JSON))

    console.print(
        Panel(
            files_table,
            title="[bold blue]Output Files[/bold blue]",
            border_style="blue",
        )
    )


if __name__ == "__main__":
    main()
