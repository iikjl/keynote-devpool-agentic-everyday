"""GitHub helpers for DW triggers — post-back comments and bot-loop guards.

Pure stdlib; relies on the `gh` CLI being installed and authenticated (or a
`GITHUB_PAT` env var). Kept intentionally small so triggers can import it
without pulling in the heavier dependencies of `agent.py`.
"""

import json
import os
import subprocess
from typing import Optional

# Loop-prevention marker. Comments/content containing this string are skipped
# by triggers so a DW run doesn't trigger itself via its own comments.
DW_BOT_IDENTIFIER = "[DW-AGENTS]"


def get_github_env() -> Optional[dict]:
    """Return a minimal env with GH_TOKEN if GITHUB_PAT is set, else None.

    Returning None means subprocess will inherit the parent environment —
    which works fine when `gh auth login` has been run.
    """
    pat = os.getenv("GITHUB_PAT")
    if not pat:
        return None
    return {
        "GH_TOKEN": pat,
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }


def is_bot_content(text: Optional[str]) -> bool:
    """True if the text contains our bot identifier — indicates a DW-posted comment."""
    return bool(text) and DW_BOT_IDENTIFIER in text


def _post_comment(cmd_prefix: list[str], target_id: str, body: str) -> None:
    if not body.startswith(DW_BOT_IDENTIFIER):
        body = f"{DW_BOT_IDENTIFIER} {body}"
    cmd = cmd_prefix + [target_id, "--body", body]
    result = subprocess.run(cmd, capture_output=True, text=True, env=get_github_env())
    if result.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(cmd_prefix)}` failed: {result.stderr.strip() or 'unknown error'}"
        )


def make_issue_comment(issue_number: int | str, body: str) -> None:
    """Post a comment to an issue. Prepends DW_BOT_IDENTIFIER if missing."""
    _post_comment(["gh", "issue", "comment"], str(issue_number), body)


def make_pr_comment(pr_number: int | str, body: str) -> None:
    """Post a comment to a PR. Prepends DW_BOT_IDENTIFIER if missing."""
    _post_comment(["gh", "pr", "comment"], str(pr_number), body)


def get_run_pr_number(run_id: int | str) -> Optional[int]:
    """Return the PR number associated with a workflow run, or None.

    Used by the CI failure trigger to post back to the originating PR when
    a run failed on a PR branch. Returns None for pushes to main, manual
    dispatches without an associated PR, etc.
    """
    cmd = ["gh", "run", "view", str(run_id), "--json", "pullRequests"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=get_github_env())
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    prs = data.get("pullRequests") or []
    if prs and isinstance(prs[0], dict) and "number" in prs[0]:
        return int(prs[0]["number"])
    return None
