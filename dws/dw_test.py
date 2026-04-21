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
DW Test - Testing phase for composable pipelines.

Runs validation commands from the plan and reports results.

Usage:
    ./dws/dw_test.py --dw-id abc12345
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
@click.option("--model", type=str, default=None, help="Model to use")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory (default: from state)",
)
def main(dw_id: str, model: str, working_dir: str):
    """Run validation tests against the implementation."""
    console = Console()
    agent_name = "tester"

    # Load state
    state = load_state(dw_id)
    if not state:
        console.print(f"[red]No state found for DW ID: {dw_id}[/red]")
        console.print("Run dw_plan.py first.")
        sys.exit(1)

    if not state.plan_file:
        console.print(f"[red]No plan file in state for DW ID: {dw_id}[/red]")
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
    info_table.add_row("Phase", "Test")
    info_table.add_row("Plan File", state.plan_file)
    info_table.add_row("Model", model or "(default)")
    info_table.add_row("Agent", agent_name)

    console.print(
        Panel(
            info_table, title="[bold blue]Test Phase[/bold blue]", border_style="blue"
        )
    )
    console.print()

    # Render template
    rendered_prompt = load_and_render("test", PLAN_FILE=state.plan_file)

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
    update_phase(state, "test", "running", agent_name=agent_name)

    try:
        with console.status("[bold yellow]Running tests...[/bold yellow]"):
            response = prompt_copilot_with_retry(request)

        if response.success:
            update_phase(
                state,
                "test",
                "success",
                agent_name=agent_name,
                output=response.output,
                session_id=response.session_id,
            )
            console.print(
                Panel(
                    response.output,
                    title="[bold green]Test Success[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
        else:
            update_phase(
                state, "test", "failed", agent_name=agent_name, output=response.output
            )
            console.print(
                Panel(
                    response.output,
                    title="[bold red]Test Failed[/bold red]",
                    border_style="red",
                    padding=(1, 2),
                )
            )
            sys.exit(1)

    except Exception as e:
        update_phase(state, "test", "failed", agent_name=agent_name, output=str(e))
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
