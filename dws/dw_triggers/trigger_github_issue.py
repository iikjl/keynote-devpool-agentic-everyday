#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click",
#   "rich",
# ]
# ///
"""
GitHub Issue Trigger - poll `gh` for labeled issues and launch a DW.

Polls the current repository (via `gh issue list`) for open issues carrying a
target label (default: `dw-trigger`). Each newly-seen qualifying issue fires a
subprocess-launched DW with the issue body as the prompt. Processed issue
numbers are remembered in-memory for the life of the process.

Requires: the GitHub CLI (`gh`) authenticated against the target repo.

Usage:
    ./dws/dw_triggers/trigger_github_issue.py
    ./dws/dw_triggers/trigger_github_issue.py --label ready-for-dw --interval 30
    ./dws/dw_triggers/trigger_github_issue.py --workflow dw_plan --model gpt-4o
"""

import json
import re
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

from github import DW_BOT_IDENTIFIER, is_bot_content, make_issue_comment  # noqa: E402

DEFAULT_WORKFLOW = "dw_plan_build_review_fix"
WORKFLOW_DIRECTIVE = re.compile(
    r"^\s*/workflow[:\s]+(\S+)\s*$", re.MULTILINE | re.IGNORECASE
)


def parse_workflow_directive(body: str) -> tuple[str | None, str]:
    """Extract a `/workflow <name>` directive from the body.

    Returns (workflow_name, body_without_directive). workflow_name is None
    when no directive is present. Strips a trailing `.py` from the name.
    """
    match = WORKFLOW_DIRECTIVE.search(body)
    if not match:
        return None, body
    name = match.group(1).strip()
    if name.endswith(".py"):
        name = name[:-3]
    stripped = WORKFLOW_DIRECTIVE.sub("", body, count=1).strip()
    return name, stripped


_shutdown = False


def _handle_signal(signum, _frame) -> None:
    global _shutdown
    _shutdown = True


def fetch_issues(label: str) -> list[dict]:
    """Return open issues matching the given label."""
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--label",
        label,
        "--json",
        "number,title,body,labels",
        "--limit",
        "50",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError(
            "`gh` CLI not found. Install the GitHub CLI and authenticate."
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"`gh issue list` failed: {exc.stderr.strip()}") from exc

    return json.loads(result.stdout or "[]")


def launch_workflow(
    issue: dict,
    default_script: Path,
    model: str | None,
    working_dir: str,
    console: Console,
) -> None:
    """Subprocess-launch the DW with the issue body as prompt.

    Honors a `/workflow <name>` directive in the issue body. If the name
    resolves to a script under `dws/`, that script is used instead of
    `default_script` and the directive line is stripped from the prompt.
    """
    number = issue["number"]
    title = issue.get("title", "")
    body = (issue.get("body") or "").strip()

    if is_bot_content(title) or is_bot_content(body):
        console.print(
            f"[yellow]Issue #{number} looks bot-posted (contains {DW_BOT_IDENTIFIER}). "
            f"Skipping to prevent loop.[/yellow]"
        )
        return

    workflow_name, body = parse_workflow_directive(body)
    if workflow_name:
        override_script = DWS_DIR / f"{workflow_name}.py"
        if override_script.exists():
            workflow_script = override_script
            console.print(
                f"[cyan]Issue #{number}: /workflow directive -> {workflow_name}[/cyan]"
            )
        else:
            console.print(
                f"[yellow]Issue #{number}: /workflow '{workflow_name}' not found, "
                f"falling back to {default_script.stem}.[/yellow]"
            )
            workflow_script = default_script
    else:
        workflow_script = default_script

    prompt = body or title
    if not prompt:
        console.print(
            f"[yellow]Issue #{number} has no body or title. Skipping.[/yellow]"
        )
        return

    dw_id = uuid.uuid4().hex[:8]

    console.print(
        Panel(
            f"[cyan]Issue #{number}:[/cyan] {title}\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Prompt preview:[/cyan] {prompt[:120]}"
            + ("..." if len(prompt) > 120 else ""),
            title="[bold green]GitHub issue trigger fired[/bold green]",
            border_style="green",
        )
    )

    comment_body = (
        f"🤖 DW triggered\n\n"
        f"- Workflow: `{workflow_script.stem}`\n"
        f"- DW ID: `{dw_id}`\n"
        f"- Model: `{model or '(default)'}`\n"
        f"- Logs: `agents/{dw_id}/`\n\n"
        f"Running in the background — will not post progress updates."
    )
    try:
        make_issue_comment(number, comment_body)
    except RuntimeError as exc:
        console.print(
            f"[yellow]Could not post comment to issue #{number}: {exc}[/yellow]"
        )

    cmd = ["uv", "run", str(workflow_script), prompt, "--dw-id", dw_id]
    if model:
        cmd.extend(["--model", model])
    if working_dir:
        cmd.extend(["--working-dir", working_dir])

    subprocess.Popen(cmd, cwd=PROJECT_ROOT, start_new_session=True)
    console.print(
        f"[dim]Launched {workflow_script.name} for issue #{number} (dw_id={dw_id}) in background.[/dim]"
    )


@click.command()
@click.option(
    "--label",
    default="dw-trigger",
    show_default=True,
    help="Label that marks an issue as a DW trigger.",
)
@click.option(
    "--interval",
    default=20,
    show_default=True,
    type=int,
    help="Poll interval in seconds.",
)
@click.option(
    "--workflow",
    default=DEFAULT_WORKFLOW,
    show_default=True,
    help=(
        "Default DW script name (without .py) to launch. Per-issue overrides "
        "via a `/workflow <name>` line in the issue body."
    ),
)
@click.option("--model", default=None, help="Model override passed to the DW.")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    default=None,
    help="Working directory passed to the DW (default: project root).",
)
def main(
    label: str, interval: int, workflow: str, model: str | None, working_dir: str | None
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
            f"[cyan]Label:[/cyan] {label}\n"
            f"[cyan]Interval:[/cyan] {interval}s\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}",
            title="[bold blue]GitHub Issue Trigger[/bold blue]",
            border_style="blue",
        )
    )
    console.print("[dim]Ctrl-C to stop.[/dim]")

    processed: set[int] = set()
    effective_working_dir = working_dir or str(PROJECT_ROOT)

    while not _shutdown:
        try:
            issues = fetch_issues(label)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            time.sleep(interval)
            continue

        new_issues = [i for i in issues if i["number"] not in processed]
        if new_issues:
            console.print(
                f"[dim]Found {len(new_issues)} new issue(s) with label '{label}'.[/dim]"
            )
            for issue in new_issues:
                if _shutdown:
                    break
                launch_workflow(
                    issue, workflow_script, model, effective_working_dir, console
                )
                processed.add(issue["number"])

        for _ in range(interval):
            if _shutdown:
                break
            time.sleep(1)

    console.print("\n[yellow]Shutdown complete.[/yellow]")


if __name__ == "__main__":
    main()
