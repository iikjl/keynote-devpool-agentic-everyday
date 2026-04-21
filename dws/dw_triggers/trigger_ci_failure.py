#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click",
#   "rich",
# ]
# ///
"""
CI Failure Trigger - poll for failed GitHub Actions runs and launch a DW.

Polls `gh run list --status failure` every N seconds. For each newly-seen
failed run (optionally filtered by workflow name), fetches the failed job
output via `gh run view --log-failed` and launches a DW (default: `dw_prompt`)
with a diagnose-and-suggest-fix prompt containing the log excerpt.

Defaults to a diagnose-only workflow (`dw_prompt`) to avoid auto-editing code
on every flaky test. Pass `--workflow dw_plan_build` to opt into full fix.

Requires: the GitHub CLI (`gh`) authenticated against the target repo.

Usage:
    ./dws/dw_triggers/trigger_ci_failure.py
    ./dws/dw_triggers/trigger_ci_failure.py --workflow-name "tests.yml"
    ./dws/dw_triggers/trigger_ci_failure.py --workflow dw_plan_build --interval 120
"""

import json
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

SCRIPT_DIR = Path(__file__).resolve().parent
DWS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = DWS_DIR.parent

sys.path.insert(0, str(DWS_DIR / "dw_modules"))

from github import get_run_pr_number, make_pr_comment  # noqa: E402

MAX_LOG_CHARS = 15_000

_shutdown = False


def _handle_signal(signum, _frame) -> None:
    global _shutdown
    _shutdown = True


def fetch_failed_runs(workflow_name: str | None, limit: int) -> list[dict]:
    cmd = [
        "gh",
        "run",
        "list",
        "--status",
        "failure",
        "--json",
        "databaseId,name,displayTitle,headBranch,headSha,conclusion,url,workflowName",
        "--limit",
        str(limit),
    ]
    if workflow_name:
        cmd.extend(["--workflow", workflow_name])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError(
            "`gh` CLI not found. Install the GitHub CLI and authenticate."
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"`gh run list` failed: {exc.stderr.strip()}") from exc
    return json.loads(result.stdout or "[]")


def fetch_failed_log(run_id: int) -> str:
    cmd = ["gh", "run", "view", str(run_id), "--log-failed"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        return f"(Could not fetch failed log: {exc.stderr.strip()})"
    log = result.stdout
    if len(log) > MAX_LOG_CHARS:
        # Tail is usually more diagnostic than head for CI failures.
        log = (
            f"[... log truncated; showing last {MAX_LOG_CHARS} chars ...]\n"
            + log[-MAX_LOG_CHARS:]
        )
    return log


def build_prompt(run: dict, log: str) -> str:
    return (
        f"A GitHub Actions run failed.\n\n"
        f"Workflow: {run.get('workflowName', '?')}\n"
        f"Run title: {run.get('displayTitle', '?')}\n"
        f"Branch: {run.get('headBranch', '?')}  SHA: {run.get('headSha', '?')[:8]}\n"
        f"URL: {run.get('url', '?')}\n\n"
        f"Failed job log:\n```\n{log}\n```\n\n"
        f"Diagnose the root cause and suggest a concrete fix. "
        f"Reference specific files and line numbers from the log."
    )


def launch_workflow(
    run: dict,
    workflow_script: Path,
    model: str | None,
    working_dir: str,
    console: Console,
) -> None:
    run_id = run["databaseId"]
    title = run.get("displayTitle", "?")
    log = fetch_failed_log(run_id)
    prompt = build_prompt(run, log)
    dw_id = uuid.uuid4().hex[:8]
    pr_number = get_run_pr_number(run_id)

    console.print(
        Panel(
            f"[cyan]Run #{run_id}:[/cyan] {title}\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Associated PR:[/cyan] {'#' + str(pr_number) if pr_number else '(none)'}\n"
            f"[cyan]Log size:[/cyan] {len(log)} chars",
            title="[bold green]CI failure trigger fired[/bold green]",
            border_style="green",
        )
    )

    if pr_number is not None:
        comment_body = (
            f"🤖 DW CI-failure triage triggered\n\n"
            f"- Failed run: [{run_id}]({run.get('url', '')})\n"
            f"- Workflow: `{workflow_script.stem}`\n"
            f"- DW ID: `{dw_id}`\n"
            f"- Model: `{model or '(default)'}`\n"
            f"- Logs: `agents/{dw_id}/`\n\n"
            f"Running diagnosis in the background — will not post progress updates."
        )
        try:
            make_pr_comment(pr_number, comment_body)
        except RuntimeError as exc:
            console.print(
                f"[yellow]Could not post comment to PR #{pr_number}: {exc}[/yellow]"
            )
    else:
        console.print(
            f"[dim]Run #{run_id} has no associated PR — skipping GitHub post-back.[/dim]"
        )

    cmd = ["uv", "run", str(workflow_script), prompt, "--dw-id", dw_id]
    if model:
        cmd.extend(["--model", model])
    if working_dir:
        cmd.extend(["--working-dir", working_dir])

    subprocess.Popen(cmd, cwd=PROJECT_ROOT, start_new_session=True)
    console.print(
        f"[dim]Launched {workflow_script.name} for run #{run_id} in background.[/dim]"
    )


@click.command()
@click.option(
    "--workflow-name",
    default=None,
    help="Filter by Actions workflow file/name (e.g. 'tests.yml').",
)
@click.option(
    "--interval",
    default=60,
    show_default=True,
    type=int,
    help="Poll interval in seconds.",
)
@click.option(
    "--limit",
    default=10,
    show_default=True,
    type=int,
    help="How many recent failures to scan each cycle.",
)
@click.option(
    "--workflow",
    default="dw_prompt",
    show_default=True,
    help="DW script name (without .py) to launch. Use dw_plan_build for auto-fix.",
)
@click.option("--model", default=None, help="Model override passed to the DW.")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    default=None,
    help="Working directory passed to the DW (default: project root).",
)
def main(
    workflow_name: str | None,
    interval: int,
    limit: int,
    workflow: str,
    model: str | None,
    working_dir: str | None,
) -> None:
    console = Console()
    workflow_script = DWS_DIR / f"{workflow}.py"
    if not workflow_script.exists():
        console.print(f"[red]Workflow script not found: {workflow_script}[/red]")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    console.print(
        Panel(
            f"[cyan]Workflow filter:[/cyan] {workflow_name or '(any)'}\n"
            f"[cyan]Interval:[/cyan] {interval}s\n"
            f"[cyan]Scan limit:[/cyan] {limit}\n"
            f"[cyan]DW:[/cyan] {workflow_script.name}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}",
            title="[bold blue]CI Failure Trigger[/bold blue]",
            border_style="blue",
        )
    )
    console.print(
        "[dim]Ctrl-C to stop. Only failures seen after startup will fire.[/dim]"
    )

    # Seed processed set from current state so we don't re-fire on historical failures.
    try:
        processed: set[int] = {
            r["databaseId"] for r in fetch_failed_runs(workflow_name, limit)
        }
        console.print(
            f"[dim]Seeded with {len(processed)} existing failure(s); watching for new ones.[/dim]"
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    effective_working_dir = working_dir or str(PROJECT_ROOT)

    while not _shutdown:
        try:
            runs = fetch_failed_runs(workflow_name, limit)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            time.sleep(interval)
            continue

        new_runs = [r for r in runs if r["databaseId"] not in processed]
        if new_runs:
            console.print(f"[dim]Found {len(new_runs)} new failure(s).[/dim]")
            for run in new_runs:
                if _shutdown:
                    break
                launch_workflow(
                    run, workflow_script, model, effective_working_dir, console
                )
                processed.add(run["databaseId"])

        for _ in range(interval):
            if _shutdown:
                break
            time.sleep(1)

    console.print("\n[yellow]Shutdown complete.[/yellow]")


if __name__ == "__main__":
    main()
