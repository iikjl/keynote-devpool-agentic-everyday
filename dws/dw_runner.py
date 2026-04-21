#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click",
#   "pydantic",
#   "rich",
# ]
# ///
"""
DW Runner — wraps a composite DW execution with branch + worktree finalization.

Triggers Popen this script instead of the composite directly. The runner:
  1. Executes the composite DW (blocking on its own subprocess) while a
     watcher thread polls `agents/<dw_id>/dw_state.json` and posts a comment
     on the source issue / PR for each phase start, success, or failure.
  2. Stages + commits any edits the agent left in the worktree.
  3. Pushes the branch to origin.
  4. Opens a draft PR back to the base branch (default `main`) linking the
     source (issue / PR / failed run / file / schedule).
  5. Comments back on the source issue or PR with the new PR URL.

Each runner is its own background process, so many runs can be in flight
simultaneously — true parallelism per worktree.

Usage (typically invoked by triggers, not by hand):
    dw_runner.py <workflow_script> <prompt>
        --dw-id <id>
        --working-dir <worktree>
        --branch <branch_name>
        [--base-branch main]
        [--auto-push/--no-auto-push]
        [--source-kind issue|pr|run|file|schedule]
        [--source-ref <number-or-name>]
        [--source-url <url>]
        [--model <name>]
"""

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

SCRIPT_DIR = Path(__file__).resolve().parent
DWS_DIR = SCRIPT_DIR
PROJECT_ROOT = DWS_DIR.parent

sys.path.insert(0, str(DWS_DIR / "dw_modules"))

from github import DW_BOT_IDENTIFIER, make_issue_comment, make_pr_comment  # noqa: E402
from phase_watcher import EventKind, run_with_phase_watch  # noqa: E402

GIT_USER_NAME_FALLBACK = "DW Agent"
GIT_USER_EMAIL_FALLBACK = "dw-agent@local"

PHASE_COMMENT_SOURCES = {"issue", "pr"}


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def _post_to_source(
    source_kind: str | None,
    source_ref: str | None,
    body: str,
    console: Console,
) -> None:
    if not source_ref or source_kind not in PHASE_COMMENT_SOURCES:
        return
    try:
        if source_kind == "issue":
            make_issue_comment(source_ref, body)
        elif source_kind == "pr":
            make_pr_comment(source_ref, body)
    except RuntimeError as exc:
        console.print(
            f"[yellow]Could not post phase comment to {source_kind} #{source_ref}: {exc}[/yellow]"
        )


def make_phase_event_handler(
    source_kind: str | None,
    source_ref: str | None,
    dw_id: str,
    console: Console,
):
    """Build an `on_event` callback that posts one comment per phase event."""

    def on_event(phase: str, kind: EventKind, duration: float | None) -> None:
        phase_label = phase.replace("_", " ").title()
        if kind == "start":
            body = f"▶ **{phase_label}** phase started — DW `{dw_id}`"
        elif kind == "success":
            dur = _format_duration(duration)
            body = (
                f"✅ **{phase_label}** phase completed"
                + (f" in {dur}" if dur else "")
                + f" — DW `{dw_id}`"
            )
        elif kind == "failed":
            dur = _format_duration(duration)
            body = (
                f"❌ **{phase_label}** phase failed"
                + (f" after {dur}" if dur else "")
                + f" — DW `{dw_id}` — see `agents/{dw_id}/`"
            )
        else:
            return
        console.print(f"[dim]phase event → {phase} {kind}[/dim]")
        _post_to_source(source_kind, source_ref, body, console)

    return on_event


def run_workflow(
    workflow_script: Path,
    prompt: str,
    dw_id: str,
    working_dir: Path,
    model: str | None,
    source_kind: str | None,
    source_ref: str | None,
    console: Console,
) -> int:
    cmd = [
        "uv",
        "run",
        str(workflow_script),
        prompt,
        "--dw-id",
        dw_id,
        "--working-dir",
        str(working_dir),
    ]
    if model:
        cmd.extend(["--model", model])
    console.print(
        f"[dim]Running workflow: {workflow_script.name} (dw_id={dw_id})[/dim]"
    )
    on_event = make_phase_event_handler(source_kind, source_ref, dw_id, console)
    return run_with_phase_watch(cmd, dw_id, on_event, cwd=PROJECT_ROOT)


def ensure_git_identity(worktree: Path) -> None:
    """Set a fallback user.name/user.email for this worktree if missing."""
    for key, fallback in (
        ("user.email", GIT_USER_EMAIL_FALLBACK),
        ("user.name", GIT_USER_NAME_FALLBACK),
    ):
        check = subprocess.run(
            ["git", "config", "--get", key],
            cwd=worktree,
            capture_output=True,
            text=True,
        )
        if check.returncode != 0 or not check.stdout.strip():
            subprocess.run(
                ["git", "config", key, fallback],
                cwd=worktree,
                capture_output=True,
            )


def has_changes(worktree: Path) -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    return bool(status.stdout.strip())


def stage_and_commit(worktree: Path, dw_id: str, prompt: str, console: Console) -> bool:
    """Stage all changes and commit. Returns True if a commit was created."""
    subprocess.run(["git", "add", "-A"], cwd=worktree, capture_output=True)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=worktree,
        capture_output=True,
    )
    if diff.returncode == 0:
        console.print("[yellow]No staged changes after the workflow ran.[/yellow]")
        return False

    summary = prompt.splitlines()[0].strip() if prompt.strip() else "(no prompt)"
    if len(summary) > 60:
        summary = summary[:57].rstrip() + "..."
    message = f"DW {dw_id}: {summary}\n\n{DW_BOT_IDENTIFIER}"
    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        console.print(
            f"[red]git commit failed: {commit.stderr.strip() or 'unknown error'}[/red]"
        )
        return False
    return True


def push_branch(worktree: Path, branch: str, console: Console) -> bool:
    push = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if push.returncode != 0:
        console.print(
            f"[red]git push failed: {push.stderr.strip() or 'unknown error'}[/red]"
        )
        return False
    console.print(f"[green]Pushed branch '{branch}' to origin.[/green]")
    return True


def build_pr_body(
    dw_id: str,
    workflow_script: Path,
    branch: str,
    source_kind: str | None,
    source_ref: str | None,
    source_url: str | None,
    model: str | None,
) -> str:
    lines = [
        f"{DW_BOT_IDENTIFIER} Auto-opened draft PR from a DW run.",
        "",
        f"- DW ID: `{dw_id}`",
        f"- Workflow: `{workflow_script.stem}`",
        f"- Branch: `{branch}`",
        f"- Model: `{model or '(default)'}`",
        f"- Logs: `agents/{dw_id}/`",
    ]
    if source_kind == "issue" and source_ref:
        lines.append(f"- Source issue: closes #{source_ref}")
    elif source_kind == "pr" and source_ref:
        lines.append(f"- Source PR: refs #{source_ref}")
    elif source_kind == "run" and source_ref:
        link = source_url or f"run #{source_ref}"
        lines.append(f"- Source CI failure: {link}")
    elif source_kind == "file" and source_ref:
        lines.append(f"- Source inbox file: `{source_ref}`")
    elif source_kind == "schedule":
        lines.append("- Source: scheduled run")
    if source_url and source_kind not in {"run"}:
        lines.append(f"- Source URL: {source_url}")
    lines.extend(
        [
            "",
            "Review the changes, edit the description as needed, then mark ready for review.",
        ]
    )
    return "\n".join(lines)


def open_pr(
    worktree: Path,
    branch: str,
    base_branch: str,
    title: str,
    body: str,
    console: Console,
) -> str | None:
    cmd = [
        "gh",
        "pr",
        "create",
        "--draft",
        "--head",
        branch,
        "--base",
        base_branch,
        "--title",
        title,
        "--body",
        body,
    ]
    result = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(
            f"[red]gh pr create failed: {result.stderr.strip() or 'unknown error'}[/red]"
        )
        return None
    url = (result.stdout or "").strip().splitlines()[-1] if result.stdout else None
    if url:
        console.print(f"[green]Draft PR opened: {url}[/green]")
    return url


def comment_source(
    source_kind: str | None,
    source_ref: str | None,
    pr_url: str,
    console: Console,
) -> None:
    if not source_ref:
        return
    body = f"PR opened from DW run: {pr_url}"
    try:
        if source_kind == "issue":
            make_issue_comment(source_ref, body)
        elif source_kind == "pr":
            make_pr_comment(source_ref, body)
        else:
            return
        console.print(f"[dim]Posted PR link back to {source_kind} #{source_ref}.[/dim]")
    except RuntimeError as exc:
        console.print(
            f"[yellow]Could not comment on {source_kind} #{source_ref}: {exc}[/yellow]"
        )


@click.command(context_settings={"ignore_unknown_options": False})
@click.argument(
    "workflow_script", type=click.Path(exists=True, dir_okay=False, resolve_path=True)
)
@click.argument("prompt")
@click.option("--dw-id", required=True, help="DW ID for this run.")
@click.option(
    "--working-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Worktree path the DW edits in.",
)
@click.option("--branch", required=True, help="Branch name for the worktree.")
@click.option("--base-branch", default="main", show_default=True)
@click.option("--auto-push/--no-auto-push", default=True, show_default=True)
@click.option(
    "--source-kind",
    type=click.Choice(["issue", "pr", "run", "file", "schedule"]),
    default=None,
)
@click.option("--source-ref", default=None, help="Issue/PR number or filename.")
@click.option("--source-url", default=None, help="URL of the source for the PR body.")
@click.option("--model", default=None, help="Model override passed to the DW.")
def main(
    workflow_script: str,
    prompt: str,
    dw_id: str,
    working_dir: str,
    branch: str,
    base_branch: str,
    auto_push: bool,
    source_kind: str | None,
    source_ref: str | None,
    source_url: str | None,
    model: str | None,
) -> None:
    console = Console()
    workflow_path = Path(workflow_script)
    worktree = Path(working_dir)

    console.print(
        Panel(
            f"[cyan]Workflow:[/cyan] {workflow_path.name}\n"
            f"[cyan]DW ID:[/cyan] {dw_id}\n"
            f"[cyan]Branch:[/cyan] {branch}\n"
            f"[cyan]Worktree:[/cyan] {worktree}\n"
            f"[cyan]Source:[/cyan] {source_kind or '(none)'} {source_ref or ''}\n"
            f"[cyan]Auto-push:[/cyan] {'yes' if auto_push else 'no'}",
            title="[bold blue]DW Runner[/bold blue]",
            border_style="blue",
        )
    )

    rc = run_workflow(
        workflow_path,
        prompt,
        dw_id,
        worktree,
        model,
        source_kind,
        source_ref,
        console,
    )
    if rc != 0:
        console.print(
            f"[red]Workflow exited non-zero ({rc}). Skipping push/PR. "
            f"Worktree left at {worktree} for inspection.[/red]"
        )
        sys.exit(rc)

    if not auto_push:
        console.print("[dim]--no-auto-push set; skipping commit/push/PR.[/dim]")
        return

    if not has_changes(worktree):
        console.print(
            "[yellow]Worktree is clean — DW made no edits. No PR opened.[/yellow]"
        )
        return

    ensure_git_identity(worktree)
    if not stage_and_commit(worktree, dw_id, prompt, console):
        return

    if not push_branch(worktree, branch, console):
        return

    summary = prompt.splitlines()[0].strip() if prompt.strip() else "(no prompt)"
    if len(summary) > 70:
        summary = summary[:67].rstrip() + "..."
    title = f"DW {dw_id}: {summary}"
    body = build_pr_body(
        dw_id, workflow_path, branch, source_kind, source_ref, source_url, model
    )
    pr_url = open_pr(worktree, branch, base_branch, title, body, console)
    if pr_url:
        comment_source(source_kind, source_ref, pr_url, console)


if __name__ == "__main__":
    main()
