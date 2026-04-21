#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic",
#   "python-dotenv",
#   "click",
#   "rich",
#   "github-copilot-sdk",
# ]
# ///
"""
Run Copilot prompts using the GitHub Copilot Python SDK.

Usage:
    # One-shot query (default)
    ./dws/dw_sdk_prompt.py "Hello Copilot"

    # Interactive session
    ./dws/dw_sdk_prompt.py --interactive

    # With specific model
    ./dws/dw_sdk_prompt.py "Create a FastAPI app" --model gpt-4o

    # From different directory
    ./dws/dw_sdk_prompt.py "List files here" --working-dir /path/to/project

Key Features:
    - Uses GitHub Copilot Python SDK (github-copilot-sdk)
    - Supports both one-shot and interactive modes
    - Multi-model support (Claude, GPT-4o, Gemini)
    - Permission handler pattern (required by Copilot SDK)
"""

import asyncio
import os
import sys
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

# Add the dw_modules directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dw_modules"))


from agent_sdk import (
    AssistantMessage,
    ManagedSession,
    _events_to_messages,
    extract_text,
    extract_tool_uses,
    get_result_text,
    safe_query,
)


def generate_short_id() -> str:
    """Generate a short ID for tracking."""
    import uuid

    return str(uuid.uuid4())[:8]


async def run_one_shot_query(
    prompt: str,
    model: Optional[str],
    working_dir: str,
    allowed_tools: Optional[List[str]] = None,
) -> None:
    """Run a one-shot query using the SDK."""
    console = Console()
    dw_id = generate_short_id()

    # Display execution info
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column(style="bold cyan")
    info_table.add_column()

    info_table.add_row("DW ID", dw_id)
    info_table.add_row("Mode", "One-shot Query")
    info_table.add_row("Prompt", prompt)
    info_table.add_row("Model", model or "(default)")
    info_table.add_row("Working Dir", working_dir)
    if allowed_tools:
        info_table.add_row("Tools", ", ".join(allowed_tools))
    info_table.add_row("[bold green]SDK[/bold green]", "GitHub Copilot Python SDK")

    console.print(
        Panel(
            info_table,
            title="[bold blue]SDK Query Execution[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    try:
        with console.status("[bold yellow]Executing via Copilot SDK...[/bold yellow]"):
            response_text, error = await safe_query(prompt)
            success = error is None

            if error:
                response_text = error

        if success:
            console.print(
                Panel(
                    response_text.strip(),
                    title="[bold green]SDK Success[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
        else:
            console.print(
                Panel(
                    response_text,
                    title="[bold red]SDK Error[/bold red]",
                    border_style="red",
                    padding=(1, 2),
                )
            )

    except Exception as e:
        console.print(
            Panel(
                f"[bold red]{str(e)}[/bold red]",
                title="[bold red]Unexpected Error[/bold red]",
                border_style="red",
            )
        )


async def run_interactive_session(
    model: Optional[str],
    working_dir: str,
    context: Optional[str] = None,
) -> None:
    """Run an interactive session using the SDK."""
    console = Console()
    dw_id = generate_short_id()

    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column(style="bold cyan")
    info_table.add_column()

    info_table.add_row("DW ID", dw_id)
    info_table.add_row("Mode", "Interactive Session")
    info_table.add_row("Model", model or "(default)")
    info_table.add_row("Working Dir", working_dir)
    if context:
        info_table.add_row("Context", context)
    info_table.add_row("[bold green]SDK[/bold green]", "GitHub Copilot Python SDK")

    console.print(
        Panel(
            info_table,
            title="[bold blue]SDK Interactive Session[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    console.print("[bold yellow]Interactive Mode[/bold yellow]")
    console.print("Commands: 'exit' or 'quit' to end session")
    console.print("Just type your questions or requests\n")

    async with ManagedSession(model=model, working_dir=working_dir) as session:
        try:
            # Send initial context if provided
            if context:
                console.print(f"[dim]Setting context: {context}[/dim]\n")
                with console.status("[bold yellow]Setting context...[/bold yellow]"):
                    await session.send_and_wait(f"Context: {context}", timeout=60.0)
                    events = await session.get_messages()
                    messages = _events_to_messages(events)
                    text = get_result_text(messages)
                    if text:
                        console.print(f"[dim]Copilot: {text}[/dim]\n")

            # Interactive loop
            while True:
                try:
                    user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[yellow]Session interrupted[/yellow]")
                    break

                if user_input.lower() in ["exit", "quit"]:
                    break

                console.print()
                with console.status("[bold yellow]Thinking...[/bold yellow]"):
                    await session.send_and_wait(user_input, timeout=120.0)
                    events = await session.get_messages()
                    messages = _events_to_messages(events)

                # Display response
                response_parts = []
                tool_uses = []
                for msg in messages:
                    if isinstance(msg, AssistantMessage):
                        text = extract_text(msg)
                        if text:
                            response_parts.append(text)
                        for tool in extract_tool_uses(msg):
                            tool_uses.append(tool.name)

                if response_parts:
                    console.print("[bold green]Copilot:[/bold green]")
                    # Show last response (get_messages returns all, take recent)
                    console.print(response_parts[-1] if response_parts else "")

                if tool_uses:
                    console.print(f"\n[dim]Tools used: {', '.join(tool_uses)}[/dim]")

                console.print()

        except Exception as e:
            console.print(f"\n[bold red]Session error: {str(e)}[/bold red]")

    console.print("\n[bold green]Session ended[/bold green]")
    console.print(f"[dim]DW ID: {dw_id}[/dim]")


@click.command()
@click.argument("prompt", required=False)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Start an interactive session instead of one-shot query",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Model to use (e.g., claude-sonnet-4, gpt-4o, gemini)",
)
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory (default: current directory)",
)
@click.option(
    "--tools",
    help="Comma-separated list of allowed tools (e.g., file_read,file_write,shell)",
)
@click.option(
    "--context",
    help="Context for interactive session (e.g., 'Debugging a memory leak')",
)
def main(
    prompt: Optional[str],
    interactive: bool,
    model: Optional[str],
    working_dir: Optional[str],
    tools: Optional[str],
    context: Optional[str],
):
    """Run Copilot prompts using the Python SDK.

    Examples:
        dw_sdk_prompt.py "What is 2 + 2?"
        dw_sdk_prompt.py --interactive
        dw_sdk_prompt.py "Create hello.py" --tools file_write,file_read
    """
    if not working_dir:
        working_dir = os.getcwd()

    allowed_tools = None
    if tools:
        allowed_tools = [t.strip() for t in tools.split(",")]

    if interactive:
        if prompt:
            Console().print(
                "[yellow]Warning: Prompt ignored in interactive mode[/yellow]\n"
            )

        asyncio.run(
            run_interactive_session(
                model=model,
                working_dir=working_dir,
                context=context,
            )
        )
    else:
        if not prompt:
            Console().print("[red]Error: Prompt required for one-shot mode[/red]")
            Console().print("Use --interactive for interactive session")
            sys.exit(1)

        asyncio.run(
            run_one_shot_query(
                prompt=prompt,
                model=model,
                working_dir=working_dir,
                allowed_tools=allowed_tools,
            )
        )


if __name__ == "__main__":
    main()
