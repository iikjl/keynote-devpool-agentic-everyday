"""Branch + worktree helpers for DW triggers.

Single source of truth for: branch-type inference, slugifying, branch naming,
and creating/cleaning per-run git worktrees under `.dw-worktrees/`. Used by
every trigger so each DW run can land in its own branch + worktree, enabling
parallel runs without collisions on the shared working tree.

Pure stdlib + subprocess — kept light so triggers (uv single-file scripts)
can import it cheaply.
"""

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Iterable

BRANCH_TYPES: tuple[str, ...] = ("feature", "bugfix", "refactor")
DEFAULT_BRANCH_TYPE = "feature"

BRANCH_DIRECTIVE = re.compile(
    r"^\s*/branch[:\s]+(\S+)\s*$", re.MULTILINE | re.IGNORECASE
)

_BUGFIX_KEYWORDS = ("fix", "bug", "broken", "crash", "error", "regression", "hotfix")
_REFACTOR_KEYWORDS = (
    "refactor",
    "rename",
    "cleanup",
    "extract",
    "restructure",
    "reorganize",
    "simplify",
)


def parse_branch_directive(body: str) -> tuple[str | None, str]:
    """Extract a `/branch <type>` directive from the body.

    Returns (branch_type, body_without_directive). branch_type is None when
    no directive is present or when the type is not one of BRANCH_TYPES.
    """
    if not body:
        return None, body
    match = BRANCH_DIRECTIVE.search(body)
    if not match:
        return None, body
    candidate = match.group(1).strip().lower()
    stripped = BRANCH_DIRECTIVE.sub("", body, count=1).strip()
    if candidate not in BRANCH_TYPES:
        return None, stripped
    return candidate, stripped


def infer_branch_type(text: str) -> str:
    """Classify a prompt by keyword into one of BRANCH_TYPES."""
    if not text:
        return DEFAULT_BRANCH_TYPE
    lowered = text.lower()
    if _matches_any(lowered, _BUGFIX_KEYWORDS):
        return "bugfix"
    if _matches_any(lowered, _REFACTOR_KEYWORDS):
        return "refactor"
    return DEFAULT_BRANCH_TYPE


def _matches_any(text: str, keywords: Iterable[str]) -> bool:
    return any(re.search(rf"\b{re.escape(k)}\b", text) for k in keywords)


def slugify(text: str, max_len: int = 40) -> str:
    """Lowercase, ascii-only, hyphen-separated slug suitable for branch names."""
    if not text:
        return "untitled"
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not cleaned:
        return "untitled"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-") or cleaned[:max_len]
    return cleaned


def make_branch_name(branch_type: str, dw_id: str, slug_source: str) -> str:
    """Produce a branch name like `feature/dw-7506f011-add-metrics-endpoint`."""
    if branch_type not in BRANCH_TYPES:
        branch_type = DEFAULT_BRANCH_TYPE
    return f"{branch_type}/dw-{dw_id}-{slugify(slug_source)}"


def create_worktree(
    repo_root: Path,
    branch_name: str,
    base_ref: str = "origin/main",
) -> Path:
    """Create a `.dw-worktrees/<branch>/` worktree on a fresh branch.

    Best-effort fetches `base_ref` first so the new branch is up-to-date with
    the remote. Wipes any leftover worktree at that path. Returns the worktree
    path on success; raises RuntimeError on hard failure.
    """
    safe_subpath = branch_name.replace("/", "__")
    worktree_dir = repo_root / ".dw-worktrees" / safe_subpath
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    if worktree_dir.exists():
        cleanup_worktree(repo_root, worktree_dir)

    if "/" in base_ref:
        remote = base_ref.split("/", 1)[0]
        ref = base_ref.split("/", 1)[1]
        subprocess.run(
            ["git", "fetch", remote, ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )

    add = subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), base_ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        fallback = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if fallback.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed for '{branch_name}': "
                f"{add.stderr.strip() or fallback.stderr.strip() or 'unknown error'}"
            )

    return worktree_dir


def cleanup_worktree(repo_root: Path, worktree_path: Path) -> None:
    """Force-remove a worktree. Safe to call even if it doesn't exist."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
