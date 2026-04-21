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
DW Plan - Planning phase for composable pipelines.

Generates a structured implementation plan from a prompt.

Usage:
    ./dws/dw_plan.py "Add a health check endpoint to apps/main.py"
    ./dws/dw_plan.py "Refactor error handling" --model gpt-4o
    ./dws/dw_plan.py "Add tests" --dw-id abc12345
"""

import os
import re
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
    generate_short_id,
    prompt_copilot_with_retry,
)
from state import create_state, update_phase
from template_loader import load_and_render, slugify


def extract_plan_path(output: str) -> str:
    """Extract the plan file path from the planning agent output."""
    patterns = [
        r"specs/plan-[a-zA-Z0-9\-]+\.md",
        r"Created plan at:\s*(specs/plan-[a-zA-Z0-9\-]+\.md)",
        r"Plan file:\s*(specs/plan-[a-zA-Z0-9\-]+\.md)",
        r"`(specs/plan-[a-zA-Z0-9\-]+\.md)`",
    ]
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1) if match.groups() else match.group(0)
    raise ValueError("Could not find plan file path in output")


@click.command()
@click.argument("prompt", required=True)
@click.option("--model", type=str, default=None, help="Model to use")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory (default: current directory)",
)
@click.option(
    "--dw-id", type=str, default=None, help="DW ID (auto-generated if omitted)"
)
def main(prompt: str, model: str, working_dir: str, dw_id: str):
    """Generate an implementation plan from a prompt."""
    console = Console()

    if not dw_id:
        dw_id = generate_short_id()
    if not working_dir:
        working_dir = os.getcwd()

    agent_name = "planner"
    slug = slugify(prompt)

    # Create state
    state = create_state(
        dw_id=dw_id, prompt=prompt, working_dir=working_dir, model=model
    )

    # Display info
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column(style="bold cyan")
    info_table.add_column()
    info_table.add_row("DW ID", dw_id)
    info_table.add_row("Phase", "Plan")
    info_table.add_row("Prompt", prompt)
    info_table.add_row("Model", model or "(default)")
    info_table.add_row("Agent", agent_name)

    console.print(
        Panel(
            info_table,
            title="[bold blue]Planning Phase[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    # Render template
    rendered_prompt = load_and_render("plan", PROMPT=prompt, DW_ID=dw_id, SLUG=slug)

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
    update_phase(state, "plan", "running", agent_name=agent_name)

    try:
        with console.status("[bold yellow]Creating plan...[/bold yellow]"):
            response = prompt_copilot_with_retry(request)

        if response.success:
            # Extract plan path
            try:
                plan_path = extract_plan_path(response.output)
                state.plan_file = plan_path
                update_phase(
                    state,
                    "plan",
                    "success",
                    agent_name=agent_name,
                    output=response.output,
                    session_id=response.session_id,
                )

                console.print(
                    Panel(
                        f"Plan created at: [bold]{plan_path}[/bold]",
                        title="[bold green]Planning Success[/bold green]",
                        border_style="green",
                    )
                )
            except ValueError as e:
                update_phase(
                    state, "plan", "failed", agent_name=agent_name, output=str(e)
                )
                console.print(
                    Panel(
                        f"[red]{e}[/red]\n\nRaw output:\n{response.output[:500]}",
                        title="[bold red]Parse Error[/bold red]",
                        border_style="red",
                    )
                )
                sys.exit(3)
        else:
            update_phase(
                state, "plan", "failed", agent_name=agent_name, output=response.output
            )
            console.print(
                Panel(
                    response.output,
                    title="[bold red]Planning Failed[/bold red]",
                    border_style="red",
                )
            )
            sys.exit(1)

    except Exception as e:
        update_phase(state, "plan", "failed", agent_name=agent_name, output=str(e))
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
    files_table.add_row("State", f"agents/{dw_id}/dw_state.json")

    console.print(
        Panel(
            files_table,
            title="[bold blue]Output Files[/bold blue]",
            border_style="blue",
        )
    )


if __name__ == "__main__":
    main()
