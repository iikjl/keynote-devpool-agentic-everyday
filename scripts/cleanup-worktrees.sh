#!/usr/bin/env bash
# Remove all DW per-run git worktrees under `.dw-worktrees/` and delete any
# leftover `feature/dw-*`, `bugfix/dw-*`, `refactor/dw-*` local branches.
#
# Safe to re-run; errors on individual worktrees/branches are logged and
# skipped. Does NOT touch remote branches — push targets are left alone.
#
# Usage:
#   ./scripts/cleanup-worktrees.sh
#   DRY_RUN=1 ./scripts/cleanup-worktrees.sh    # show what would be removed

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "${REPO_ROOT:-}" ]; then
  echo "Not inside a git repository." >&2
  exit 1
fi

cd "$REPO_ROOT"

DRY_RUN="${DRY_RUN:-0}"

removed_worktrees=0
removed_branches=0

# Worktrees under .dw-worktrees/
while IFS= read -r wt; do
  [ -z "$wt" ] && continue
  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] git worktree remove --force $wt"
  else
    if git worktree remove --force "$wt" 2>/dev/null; then
      echo "Removed worktree: $wt"
      removed_worktrees=$((removed_worktrees + 1))
    else
      echo "Could not remove worktree: $wt" >&2
    fi
  fi
done < <(git worktree list --porcelain | awk '/^worktree / {print $2}' | grep -F "/.dw-worktrees/" || true)

# Prune any stale worktree admin records.
if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] git worktree prune"
else
  git worktree prune
fi

# Local DW branches
while IFS= read -r br; do
  [ -z "$br" ] && continue
  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] git branch -D $br"
  else
    if git branch -D "$br" >/dev/null 2>&1; then
      echo "Deleted branch: $br"
      removed_branches=$((removed_branches + 1))
    else
      echo "Could not delete branch: $br" >&2
    fi
  fi
done < <(git for-each-ref --format='%(refname:short)' refs/heads/feature/dw-* refs/heads/bugfix/dw-* refs/heads/refactor/dw-* 2>/dev/null || true)

if [ "$DRY_RUN" != "1" ]; then
  echo "Done. Removed $removed_worktrees worktree(s) and $removed_branches branch(es)."
fi
