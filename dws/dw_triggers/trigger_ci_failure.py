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
output via `gh run view --log-failed` and launches a DW with a
diagnose-and-suggest-fix prompt containing the log excerpt.

Defaults to a diagnose-only workflow (`dw_prompt`) to avoid auto-editing code
on every flaky test. Pass `--workflow dw_plan_build` to opt into full fix —
auto-fix runs land in a per-run `bugfix/` branch + worktree and open a draft
PR back to main when complete. Diagnose-only runs do not branch.

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

from branching import create_worktree, make_branch_name  # noqa: E402
from github import get_run_pr_number, make_pr_comment  # noqa: E402

MAX_LOG_CHARS = 15_000
RUNNER_SCRIPT = DWS_DIR / "dw_runner.py"
DIAGNOSE_ONLY_WORKFLOWS = {"dw_prompt"}

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
    fallback_working_dir: str,
    console: Console,
) -> None:
    run_id = run["databaseId"]
    title = run.get("displayTitle", "?")
    log = fetch_failed_log(run_id)
    prompt = build_prompt(run, log)
    dw_id = uuid.uuid4().hex[:8]
    pr_number = get_run_pr_number(run_id)
    diagnose_only = workflow_script.stem in DIAGNOSE_ONLY_WORKFLOWS

    if diagnose_only:
        branch_name = None
        effective_working_dir = fallback_working_dir
        worktree_note = "(shared working dir — diagnose-only, no branch)"
        auto_push_flag = "--no-auto-push"
    else:
        branch_name = make_branch_name("bugfix", dw_id, f"ci-{run_id}")
        try:
            worktree = create_worktree(PROJECT_ROOT, branch_name)
            effective_working_dir = str(worktree)
            worktree_note = f"`{worktree.relative_to(PROJECT_ROOT)}`"
            auto_push_flag = "--auto-push"
        except RuntimeError as exc:
            console.print(
                f"[yellow]Worktree creation failed for run #{run_id}: {exc}. "
                f"Falling back to shared dir, no auto-PR.[/yellow]"
            )
            effective_working_dir = fallback_working_dir
            worktree_note = "(shared working dir — no branch)"
            auto_push_flag = "--no-auto-push"

    console.print(
        Panel(
            f"[cyan]Run #{run_id}:[/cyan] {title}\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Branch:[/cyan] {branch_name or '(none — diagnose-only)'}\n"
            f"[cyan]Worktree:[/cyan] {worktree_note}\n"
            f"[cyan]Associated PR:[/cyan] {'#' + str(pr_number) if pr_number else '(none)'}\n"
            f"[cyan]Log size:[/cyan] {len(log)} chars",
            title="[bold green]CI failure trigger fired[/bold green]",
            border_style="green",
        )
    )

    if pr_number is not None:
        comment_body = (
            f"DW CI-failure triage triggered\n\n"
            f"- Failed run: [{run_id}]({run.get('url', '')})\n"
            f"- Workflow: `{workflow_script.stem}`\n"
            f"- DW ID: `{dw_id}`\n"
            f"- Branch: `{branch_name or '(diagnose-only)'}`\n"
            f"- Worktree: {worktree_note}\n"
            f"- Model: `{model or '(default)'}`\n"
            f"- Logs: `agents/{dw_id}/`\n\n"
            + (
                "A draft PR will be opened automatically once the workflow finishes."
                if branch_name
                else "Diagnose-only — no edits will be made."
            )
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

    cmd = [
        "uv",
        "run",
        str(RUNNER_SCRIPT),
        str(workflow_script),
        prompt,
        "--dw-id",
        dw_id,
        "--working-dir",
        effective_working_dir,
        "--branch",
        branch_name or f"bugfix/dw-{dw_id}-noop",
        auto_push_flag,
    ]
    if pr_number is not None:
        cmd.extend(["--source-kind", "pr", "--source-ref", str(pr_number)])
    else:
        cmd.extend(["--source-kind", "run", "--source-ref", str(run_id)])
    if run.get("url"):
        cmd.extend(["--source-url", run["url"]])
    if model:
        cmd.extend(["--model", model])

    subprocess.Popen(cmd, cwd=PROJECT_ROOT, start_new_session=True)
    console.print(f"[dim]Launched runner for run #{run_id} in background.[/dim]")


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
    help="Fallback working directory (used for diagnose-only or worktree-failure).",
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
    if not RUNNER_SCRIPT.exists():
        console.print(f"[red]Runner script not found: {RUNNER_SCRIPT}[/red]")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    console.print(
        Panel(
            f"[cyan]Workflow filter:[/cyan] {workflow_name or '(any)'}\n"
            f"[cyan]Interval:[/cyan] {interval}s\n"
            f"[cyan]Scan limit:[/cyan] {limit}\n"
            f"[cyan]DW:[/cyan] {workflow_script.name}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}\n"
            f"[cyan]Mode:[/cyan] "
            + (
                "diagnose-only (no branch)"
                if workflow_script.stem in DIAGNOSE_ONLY_WORKFLOWS
                else "auto-fix (bugfix/ branch + draft PR)"
            ),
            title="[bold blue]CI Failure Trigger[/bold blue]",
            border_style="blue",
        )
    )
    console.print(
        "[dim]Ctrl-C to stop. Only failures seen after startup will fire.[/dim]"
    )

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

    fallback_working_dir = working_dir or str(PROJECT_ROOT)

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
                    run, workflow_script, model, fallback_working_dir, console
                )
                processed.add(run["databaseId"])

        for _ in range(interval):
            if _shutdown:
                break
            time.sleep(1)

    console.print("\n[yellow]Shutdown complete.[/yellow]")


if __name__ == "__main__":
    main()
