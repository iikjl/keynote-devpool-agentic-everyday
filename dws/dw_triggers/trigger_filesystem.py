#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click",
#   "rich",
#   "watchdog",
# ]
# ///
"""
Filesystem Trigger - watch a directory for new prompt files and launch a DW.

Drops a `.md` file into the watched directory (default: `dw_inbox/`), and this
trigger creates a per-run git branch + worktree under `.dw-worktrees/`, then
fires the DW via `dw_runner.py`. The runner pushes the branch and opens a
draft PR back to `main` after the workflow finishes. Processed files are
renamed with a `.processed` suffix so they won't fire again.

Usage:
    ./dws/dw_triggers/trigger_filesystem.py
    ./dws/dw_triggers/trigger_filesystem.py --watch-dir some/other/dir
    ./dws/dw_triggers/trigger_filesystem.py --workflow dw_plan --model gpt-4o
"""

import subprocess
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

SCRIPT_DIR = Path(__file__).resolve().parent
DWS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = DWS_DIR.parent

sys.path.insert(0, str(DWS_DIR / "dw_modules"))

from agent import generate_short_id  # noqa: E402
from branching import (
    create_worktree,
    infer_branch_type,  # noqa: E402
    make_branch_name,
    parse_branch_directive,
)

RUNNER_SCRIPT = DWS_DIR / "dw_runner.py"


class PromptFileHandler(FileSystemEventHandler):
    def __init__(
        self,
        console: Console,
        workflow: str,
        model: str | None,
        fallback_working_dir: str,
    ) -> None:
        self.console = console
        self.workflow_script = DWS_DIR / f"{workflow}.py"
        self.model = model
        self.fallback_working_dir = fallback_working_dir

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        self._handle(Path(event.src_path))

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        self._handle(Path(event.dest_path))

    def _handle(self, path: Path) -> None:
        if path.suffix != ".md" or path.name.endswith(".processed.md"):
            return

        try:
            raw = path.read_text().strip()
        except OSError as exc:
            self.console.print(f"[red]Could not read {path}: {exc}[/red]")
            return

        if not raw:
            self.console.print(f"[yellow]Skipping empty file {path.name}[/yellow]")
            return

        branch_directive, prompt = parse_branch_directive(raw)
        if not prompt:
            self.console.print(
                f"[yellow]Skipping {path.name} — only a directive, no prompt body.[/yellow]"
            )
            return

        dw_id = generate_short_id()
        branch_type = branch_directive or infer_branch_type(prompt)
        branch_name = make_branch_name(branch_type, dw_id, path.stem)

        try:
            worktree = create_worktree(PROJECT_ROOT, branch_name)
            effective_working_dir = str(worktree)
            worktree_note = str(worktree.relative_to(PROJECT_ROOT))
            auto_push_flag = "--auto-push"
        except RuntimeError as exc:
            self.console.print(
                f"[yellow]Worktree creation failed for {path.name}: {exc}. "
                f"Falling back to shared dir, no auto-PR.[/yellow]"
            )
            effective_working_dir = self.fallback_working_dir
            worktree_note = "(shared working dir — no branch)"
            auto_push_flag = "--no-auto-push"

        self.console.print(
            Panel(
                f"[cyan]File:[/cyan] {path.name}\n"
                f"[cyan]Workflow:[/cyan] {self.workflow_script.name}\n"
                f"[cyan]DW ID:[/cyan] {dw_id}\n"
                f"[cyan]Branch:[/cyan] {branch_name}\n"
                f"[cyan]Worktree:[/cyan] {worktree_note}\n"
                f"[cyan]Prompt preview:[/cyan] {prompt[:120]}"
                + ("..." if len(prompt) > 120 else ""),
                title="[bold green]Filesystem trigger fired[/bold green]",
                border_style="green",
            )
        )

        cmd = [
            "uv",
            "run",
            str(RUNNER_SCRIPT),
            str(self.workflow_script),
            prompt,
            "--dw-id",
            dw_id,
            "--working-dir",
            effective_working_dir,
            "--branch",
            branch_name,
            auto_push_flag,
            "--source-kind",
            "file",
            "--source-ref",
            path.name,
        ]
        if self.model:
            cmd.extend(["--model", self.model])

        processed = path.with_suffix(".processed.md")
        try:
            path.rename(processed)
        except OSError as exc:
            self.console.print(
                f"[red]Could not rename {path}: {exc}. Skipping to avoid duplicate fires.[/red]"
            )
            return

        subprocess.Popen(cmd, cwd=PROJECT_ROOT, start_new_session=True)
        self.console.print(
            f"[dim]Launched runner in background. Marked input as {processed.name}.[/dim]"
        )


@click.command()
@click.option(
    "--watch-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default="dw_inbox",
    show_default=True,
    help="Directory to watch for new prompt files (relative to project root).",
)
@click.option(
    "--workflow",
    default="dw_plan_build",
    show_default=True,
    help="DW script name (without .py) to launch for each new file.",
)
@click.option("--model", default=None, help="Model override passed to the DW.")
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    default=None,
    help="Fallback working directory when worktree creation fails.",
)
def main(
    watch_dir: str, workflow: str, model: str | None, working_dir: str | None
) -> None:
    console = Console()
    target = (PROJECT_ROOT / watch_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    workflow_script = DWS_DIR / f"{workflow}.py"
    if not workflow_script.exists():
        console.print(f"[red]Workflow script not found: {workflow_script}[/red]")
        sys.exit(1)
    if not RUNNER_SCRIPT.exists():
        console.print(f"[red]Runner script not found: {RUNNER_SCRIPT}[/red]")
        sys.exit(1)

    console.print(
        Panel(
            f"[cyan]Watching:[/cyan] {target}\n"
            f"[cyan]Workflow:[/cyan] {workflow_script.name}\n"
            f"[cyan]Model:[/cyan] {model or '(default)'}\n"
            f"[cyan]Mode:[/cyan] branch + worktree per file, auto draft PR",
            title="[bold blue]Filesystem Trigger[/bold blue]",
            border_style="blue",
        )
    )
    console.print(
        "[dim]Drop any .md file into the watched dir to fire the workflow. "
        "Optional `/branch <type>` directive in the file body. Ctrl-C to stop.[/dim]"
    )

    handler = PromptFileHandler(
        console=console,
        workflow=workflow,
        model=model,
        fallback_working_dir=working_dir or str(PROJECT_ROOT),
    )
    observer = Observer()
    observer.schedule(handler, str(target), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
