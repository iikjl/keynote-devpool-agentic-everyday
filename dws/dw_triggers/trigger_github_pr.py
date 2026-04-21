#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click",
#   "rich",
# ]
# ///
"""
GitHub PR Trigger - poll for labeled PRs and launch a DW with the PR diff.

Polls `gh pr list --label <label>` for open pull requests. On each newly-seen
qualifying PR, fetches the diff via `gh pr diff <number>` and launches a DW
(default: `dw_prompt`) with a prompt containing PR metadata and the diff —
suitable for an ad-hoc review or patch-suggestion pass.

Requires: the GitHub CLI (`gh`) authenticated against the target repo.

Usage:
    ./dws/dw_triggers/trigger_github_pr.py
    ./dws/dw_triggers/trigger_github_pr.py --label dw-review --interval 60
    ./dws/dw_triggers/trigger_github_pr.py --workflow dw_plan_build_review_fix
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

from github import DW_BOT_IDENTIFIER, is_bot_content, make_pr_comment  # noqa: E402

MAX_DIFF_CHARS = 20_000

_shutdown = False


def _handle_signal(signum, _frame) -> None:
    global _shutdown
    _shutdown = True


def fetch_prs(label: str) -> list[dict]:
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        "open",
        "--label",
        label,
        "--json",
        "number,title,body,headRefName,baseRefName,author,url",
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
        raise RuntimeError(f"`gh pr list` failed: {exc.stderr.strip()}") from exc
    return json.loads(result.stdout or "[]")


def fetch_diff(pr_number: int) -> str:
    cmd = ["gh", "pr", "diff", str(pr_number)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        return f"(Could not fetch diff: {exc.stderr.strip()})"
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = (
            diff[:MAX_DIFF_CHARS]
            + f"\n\n[... diff truncated at {MAX_DIFF_CHARS} chars ...]"
        )
    return diff


def build_prompt(pr: dict, diff: str) -> str:
    number = pr["number"]
    title = pr.get("title", "")
    body = (pr.get("body") or "").strip() or "(no description)"
    head = pr.get("headRefName", "?")
    base = pr.get("baseRefName", "?")
    author = (pr.get("author") or {}).get("login", "?")

    return (
        f"Review the following pull request and provide actionable feedback.\n\n"
        f"PR #{number}: {title}\n"
        f"Author: @{author}\n"
        f"Branch: {head} -> {base}\n\n"
        f"Description:\n{body}\n\n"
        f"Diff:\n```diff\n{diff}\n```\n\n"
        f"Focus on correctness, security, and maintainability. "
        f"Call out concrete bugs and suggest specific fixes."
    )


def prepare_worktree(pr_number: int, console: Console) -> Path | None:
    """Create a git worktree for the PR under `.dw-worktrees/pr-<number>`.

    The worktree is checked out to the PR head (detached) via `gh pr checkout
    --detach`, so the DW can modify files without touching the main working
    tree. Returns the path on success, or None if worktree creation failed
    — in which case the caller should fall back to the shared working dir
    (or skip, depending on policy).
    """
    worktree_dir = PROJECT_ROOT / ".dw-worktrees" / f"pr-{pr_number}"
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    # Wipe any leftover worktree from a prior run so we start clean.
    if worktree_dir.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_dir)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

    add = subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_dir), "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        console.print(
            f"[yellow]Worktree add failed for PR #{pr_number}: "
            f"{add.stderr.strip() or 'unknown error'}[/yellow]"
        )
        return None

    checkout = subprocess.run(
        ["gh", "pr", "checkout", "--detach", str(pr_number)],
        cwd=worktree_dir,
        capture_output=True,
        text=True,
    )
    if checkout.returncode != 0:
        console.print(
            f"[yellow]`gh pr checkout` failed for PR #{pr_number}: "
            f"{checkout.stderr.strip() or 'unknown error'}[/yellow]"
        )
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_dir)],
            cwd=PROJECT_ROOT,
            capture_output=True,
        )
        return None

    return worktree_dir


def launch_workflow(
    pr: dict,
    workflow_script: Path,
    model: str | None,
    working_dir: str,
    isolated: bool,
    console: Console,
) -> None:
    number = pr["number"]
    title = pr.get("title", "")
    body = pr.get("body") or ""

    if is_bot_content(title) or is_bot_content(body):
        console.print(
            f"[yellow]PR #{number} looks bot-posted (contains {DW_BOT_IDENTIFIER}). "
            f"Skipping to prevent loop.[/yellow]"
        )
        return

    diff = fetch_diff(number)
    prompt = build_prompt(pr, diff)
    dw_id = uuid.uuid4().hex[:8]

    effective_working_dir = working_dir
    worktree_note = "(shared working dir)"
    if isolated:
        worktree = prepare_worktree(number, console)
        if worktree is not None:
            effective_working_dir = str(worktree)
            worktree_note = f"worktree: `{worktree.relative_to(PROJECT_ROOT)}`"
        else:
            console.print(
                f"[yellow]Falling back to shared working dir for PR #{number}.[/yellow]"
            )
            worktree_note = "(worktree unavailable — shared working dir)"

    console.print(
        Panel(
            f"[cyan]PR #{number}:[/cyan] {title}\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Working dir:[/cyan] {effective_working_dir}\n"
            f"[cyan]Diff size:[/cyan] {len(diff)} chars",
            title="[bold green]PR trigger fired[/bold green]",
            border_style="green",
        )
    )

    comment_body = (
        f"🤖 DW review triggered\n\n"
        f"- Workflow: `{workflow_script.stem}`\n"
        f"- DW ID: `{dw_id}`\n"
        f"- Model: `{model or '(default)'}`\n"
        f"- Working dir: {worktree_note}\n"
        f"- Diff size: {len(diff)} chars\n"
        f"- Logs: `agents/{dw_id}/`\n\n"
        f"Running in the background — will post a comment per phase as it progresses."
    )
    try:
        make_pr_comment(number, comment_body)
    except RuntimeError as exc:
        console.print(f"[yellow]Could not post comment to PR #{number}: {exc}[/yellow]")

    runner_script = DWS_DIR / "dw_runner.py"
    pr_url = (pr.get("url") or "").strip() or None
    cmd = [
        "uv",
        "run",
        str(runner_script),
        str(workflow_script),
        prompt,
        "--dw-id",
        dw_id,
        "--working-dir",
        effective_working_dir,
        "--branch",
        f"pr-{number}",
        "--no-auto-push",
        "--source-kind",
        "pr",
        "--source-ref",
        str(number),
    ]
    if pr_url:
        cmd.extend(["--source-url", pr_url])
    if model:
        cmd.extend(["--model", model])

    subprocess.Popen(cmd, cwd=PROJECT_ROOT, start_new_session=True)
    console.print(
        f"[dim]Launched dw_runner.py → {workflow_script.name} for PR #{number} "
        f"in background (phase comments enabled).[/dim]"
    )


@click.command()
@click.option(
    "--label",
    default="dw-review",
    show_default=True,
    help="Label that marks a PR for DW review.",
)
@click.option(
    "--interval",
    default=60,
    show_default=True,
    type=int,
    help="Poll interval in seconds.",
)
@click.option(
    "--workflow",
    default="dw_plan_security_review_patch",
    show_default=True,
    help=(
        "DW script name (without .py) to launch. Default runs plan + "
        "security review + patch loop. Use `dw_prompt` for diagnose-only."
    ),
)
@click.option("--model", default=None, help="Model override passed to the DW.")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    default=None,
    help="Working directory passed to the DW when --no-isolated is set.",
)
@click.option(
    "--isolated/--no-isolated",
    default=True,
    show_default=True,
    help=(
        "Create a git worktree per PR under .dw-worktrees/pr-<num> and run "
        "the DW there, so patches don't touch the shared working tree. "
        "Requires `git` + `gh` to work on the current repo."
    ),
)
def main(
    label: str,
    interval: int,
    workflow: str,
    model: str | None,
    working_dir: str | None,
    isolated: bool,
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
            f"[cyan]Model:[/cyan] {model or '(default)'}\n"
            f"[cyan]Isolated:[/cyan] {'yes (git worktree per PR)' if isolated else 'no (shared working tree)'}",
            title="[bold blue]GitHub PR Trigger[/bold blue]",
            border_style="blue",
        )
    )
    console.print("[dim]Ctrl-C to stop.[/dim]")

    processed: set[int] = set()
    effective_working_dir = working_dir or str(PROJECT_ROOT)

    while not _shutdown:
        try:
            prs = fetch_prs(label)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            time.sleep(interval)
            continue

        new_prs = [p for p in prs if p["number"] not in processed]
        if new_prs:
            console.print(
                f"[dim]Found {len(new_prs)} new PR(s) with label '{label}'.[/dim]"
            )
            for pr in new_prs:
                if _shutdown:
                    break
                launch_workflow(
                    pr,
                    workflow_script,
                    model,
                    effective_working_dir,
                    isolated,
                    console,
                )
                processed.add(pr["number"])

        for _ in range(interval):
            if _shutdown:
                break
            time.sleep(1)

    console.print("\n[yellow]Shutdown complete.[/yellow]")


if __name__ == "__main__":
    main()
