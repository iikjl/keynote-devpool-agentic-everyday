#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click",
#   "rich",
#   "schedule",
# ]
# ///
"""
Schedule Trigger - time-driven DW runs (nightly security review, periodic sweeps).

Unlike the polling triggers, this fires on a fixed interval regardless of
external events. Use it for recurring batch work: a nightly
`dw_security_review`, a weekly `dw_plan_build_test` sanity pass, etc.

Interval accepts simple suffixed values: `30s`, `15m`, `6h`, `1d`.

Usage:
    # Every 6 hours, run dw_plan_build with a fixed prompt
    ./dws/dw_triggers/trigger_schedule.py \\
        --every 6h \\
        --prompt "Audit apps/main.py for dead code and propose removals"

    # Daily at 02:00 local time, security review
    ./dws/dw_triggers/trigger_schedule.py \\
        --at 02:00 \\
        --workflow dw_prompt \\
        --prompt "Review apps/main.py for OWASP top 10 issues"

    # Run once immediately then exit (useful for cron-managed schedules)
    ./dws/dw_triggers/trigger_schedule.py --once --prompt "..."
"""

import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import click
import schedule
from rich.console import Console
from rich.panel import Panel

SCRIPT_DIR = Path(__file__).resolve().parent
DWS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = DWS_DIR.parent

_shutdown = False


def _handle_signal(signum, _frame) -> None:
    global _shutdown
    _shutdown = True


def parse_interval(spec: str) -> tuple[int, str]:
    """Parse '15m', '6h', '30s', '1d' into (count, unit-for-schedule)."""
    match = re.fullmatch(r"(\d+)([smhd])", spec.strip().lower())
    if not match:
        raise click.BadParameter(
            f"Invalid interval '{spec}'. Use forms like 30s, 15m, 6h, 1d."
        )
    count = int(match.group(1))
    unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[match.group(2)]
    return count, unit


def launch_workflow(
    prompt: str,
    workflow_script: Path,
    model: str | None,
    working_dir: str,
    console: Console,
) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(
        Panel(
            f"[cyan]Time:[/cyan] {timestamp}\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]Prompt preview:[/cyan] {prompt[:120]}"
            + ("..." if len(prompt) > 120 else ""),
            title="[bold green]Schedule trigger fired[/bold green]",
            border_style="green",
        )
    )

    cmd = ["uv", "run", str(workflow_script), prompt]
    if model:
        cmd.extend(["--model", model])
    if working_dir:
        cmd.extend(["--working-dir", working_dir])

    subprocess.Popen(cmd, cwd=PROJECT_ROOT, start_new_session=True)
    console.print(f"[dim]Launched {workflow_script.name} in background.[/dim]")


@click.command()
@click.option("--prompt", required=True, help="Prompt to send to the DW on each fire.")
@click.option(
    "--every",
    "interval_spec",
    default=None,
    help="Fire on interval (e.g. 30s, 15m, 6h, 1d).",
)
@click.option(
    "--at",
    "at_time",
    default=None,
    help="Fire daily at a wall-clock time (HH:MM, 24h).",
)
@click.option(
    "--once",
    is_flag=True,
    help="Fire exactly once and exit (useful under system cron).",
)
@click.option(
    "--workflow",
    default="dw_plan_build",
    show_default=True,
    help="DW script name (without .py) to launch.",
)
@click.option("--model", default=None, help="Model override passed to the DW.")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    default=None,
    help="Working directory passed to the DW (default: project root).",
)
def main(
    prompt: str,
    interval_spec: str | None,
    at_time: str | None,
    once: bool,
    workflow: str,
    model: str | None,
    working_dir: str | None,
) -> None:
    console = Console()

    modes = [bool(interval_spec), bool(at_time), once]
    if sum(modes) != 1:
        raise click.UsageError("Specify exactly one of --every, --at, or --once.")

    workflow_script = DWS_DIR / f"{workflow}.py"
    if not workflow_script.exists():
        console.print(f"[red]Workflow script not found: {workflow_script}[/red]")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    effective_working_dir = working_dir or str(PROJECT_ROOT)

    def fire() -> None:
        launch_workflow(prompt, workflow_script, model, effective_working_dir, console)

    if once:
        console.print(
            Panel(
                f"[cyan]Mode:[/cyan] once\n"
                f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
                f"[cyan]Model:[/cyan] {model or '(default)'}",
                title="[bold blue]Schedule Trigger[/bold blue]",
                border_style="blue",
            )
        )
        fire()
        return

    if interval_spec:
        count, unit = parse_interval(interval_spec)
        job = getattr(schedule.every(count), unit).do(fire)
        mode_label = f"every {count} {unit}"
    else:
        if not re.fullmatch(r"[0-2]\d:[0-5]\d", at_time or ""):
            raise click.BadParameter(f"--at must be HH:MM (24h), got '{at_time}'.")
        job = schedule.every().day.at(at_time).do(fire)
        mode_label = f"daily at {at_time}"

    console.print(
        Panel(
            f"[cyan]Mode:[/cyan] {mode_label}\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}\n"
            f"[cyan]Next run:[/cyan] {job.next_run}",
            title="[bold blue]Schedule Trigger[/bold blue]",
            border_style="blue",
        )
    )
    console.print("[dim]Ctrl-C to stop.[/dim]")

    while not _shutdown:
        schedule.run_pending()
        time.sleep(1)

    console.print("\n[yellow]Shutdown complete.[/yellow]")


if __name__ == "__main__":
    main()
