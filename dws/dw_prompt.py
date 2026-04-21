#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pydantic",
#   "python-dotenv",
#   "click",
#   "rich",
# ]
# ///
"""
Run an adhoc Copilot prompt from the command line.

Usage:
    # Method 1: Direct execution (requires uv)
    ./dw_prompt.py "Write a hello world Python script"

    # Method 2: Using uv run
    uv run dw_prompt.py "Write a hello world Python script"

    # Method 3: Using Python directly (requires dependencies installed)
    python dw_prompt.py "Write a hello world Python script"

Examples:
    # Run with specific model
    ./dw_prompt.py "Explain this code" --model gpt-4o

    # Run with custom output file
    ./dw_prompt.py "Create a FastAPI app" --output my_result.jsonl

    # Run from a different working directory
    ./dw_prompt.py "List files here" --working-dir /path/to/project

    # Disable retry on failure
    ./dw_prompt.py "Quick test" --no-retry

    # Use custom agent name
    ./dw_prompt.py "Debug this" --agent-name debugger
"""

import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add the dw_modules directory to the path so we can import agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dw_modules"))

from agent import (
    CopilotPromptRequest,
    CopilotPromptResponse,
    generate_short_id,
    prompt_copilot,
    prompt_copilot_with_retry,
)

# Output file name constants
OUTPUT_JSONL = "cp_raw_output.jsonl"
OUTPUT_JSON = "cp_raw_output.json"
FINAL_OBJECT_JSON = "cp_final_object.json"
SUMMARY_JSON = "custom_summary_output.json"


@click.command()
@click.argument("prompt", required=True)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model to use (e.g., claude-sonnet-4, gpt-4o, gemini)",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Output file path (default: ./agents/<id>/<agent>/cp_raw_output.jsonl)",
)
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory for the prompt execution (default: current directory)",
)
@click.option("--no-retry", is_flag=True, help="Disable automatic retry on failure")
@click.option(
    "--agent-name", default="oneoff", help="Agent name for tracking (default: oneoff)"
)
@click.option(
    "--dw-id", type=str, default=None, help="DW ID (auto-generated if omitted)"
)
def main(
    prompt: str,
    model: str,
    output: str,
    working_dir: str,
    no_retry: bool,
    agent_name: str,
    dw_id: str,
):
    """Run an adhoc Copilot prompt from the command line."""
    console = Console()

    if not dw_id:
        dw_id = generate_short_id()

    # Set up output file path
    if not output:
        output_dir = Path(f"./agents/{dw_id}/{agent_name}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output = str(output_dir / OUTPUT_JSONL)

    # Use current directory if no working directory specified
    if not working_dir:
        working_dir = os.getcwd()

    # Create the prompt request
    request = CopilotPromptRequest(
        prompt=prompt,
        dw_id=dw_id,
        agent_name=agent_name,
        model=model,
        auto_approve=True,
        output_file=output,
        working_dir=working_dir,
    )

    # Create execution info table
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column(style="bold cyan")
    info_table.add_column()

    info_table.add_row("DW ID", dw_id)
    info_table.add_row("DW Name", "dw_prompt")
    info_table.add_row("SDK", "GitHub Copilot SDK")
    info_table.add_row("Prompt", prompt)
    info_table.add_row("Model", model or "(default)")
    info_table.add_row("Working Dir", working_dir)
    info_table.add_row("Output", output)

    console.print(
        Panel(
            info_table,
            title="[bold blue]Inputs[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    response: CopilotPromptResponse | None = None

    try:
        # Execute the prompt
        with console.status(
            "[bold yellow]Executing prompt via Copilot...[/bold yellow]"
        ):
            if no_retry:
                response = prompt_copilot(request)
            else:
                response = prompt_copilot_with_retry(request)

        # Display the result
        if response.success:
            result_panel = Panel(
                response.output,
                title="[bold green]Success[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(result_panel)

            if response.session_id:
                console.print(
                    f"\n[bold cyan]Session ID:[/bold cyan] {response.session_id}"
                )
        else:
            error_panel = Panel(
                response.output,
                title="[bold red]Failed[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)

            if response.retry_code != "none":
                console.print(
                    f"\n[bold yellow]Retry code:[/bold yellow] {response.retry_code}"
                )

        # Show output file info
        console.print()

        # Create a JSON summary file
        if output.endswith(f"/{OUTPUT_JSONL}"):
            simple_json_output = output.replace(f"/{OUTPUT_JSONL}", f"/{SUMMARY_JSON}")
        else:
            simple_json_output = output.replace(".jsonl", "_summary.json")

        with open(simple_json_output, "w") as f:
            json.dump(
                {
                    "dw_id": dw_id,
                    "sdk": "copilot",
                    "prompt": prompt,
                    "model": model,
                    "working_dir": working_dir,
                    "success": response.success,
                    "session_id": response.session_id,
                    "retry_code": response.retry_code,
                    "output": response.output,
                },
                f,
                indent=2,
            )

        # Files saved panel
        files_table = Table(show_header=True, box=None)
        files_table.add_column("File Type", style="bold cyan")
        files_table.add_column("Path", style="dim")
        files_table.add_column("Description", style="italic")

        output_dir = os.path.dirname(output)
        json_array_path = os.path.join(output_dir, OUTPUT_JSON)
        final_object_path = os.path.join(output_dir, FINAL_OBJECT_JSON)

        files_table.add_row("JSONL Stream", output, "Raw streaming output from Copilot")
        files_table.add_row(
            "JSON Array", json_array_path, "All messages as a JSON array"
        )
        files_table.add_row(
            "Final Object", final_object_path, "Last message entry (final result)"
        )
        files_table.add_row(
            "Summary", simple_json_output, "High-level execution summary with metadata"
        )

        console.print(
            Panel(
                files_table,
                title="[bold blue]Output Files[/bold blue]",
                border_style="blue",
            )
        )

        sys.exit(0 if response.success else 1)

    except Exception as e:
        console.print(
            Panel(
                f"[bold red]{str(e)}[/bold red]",
                title="[bold red]Unexpected Error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
