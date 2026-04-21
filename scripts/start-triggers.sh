#!/usr/bin/env bash
# Start one or more DW triggers in the background. Portable across macOS/Linux.
#
# Usage:
#   ./scripts/start-triggers.sh filesystem
#   ./scripts/start-triggers.sh github-issue github-pr ci-failure
#   ./scripts/start-triggers.sh all
#
# Logs go to logs/triggers/<name>.log. Stop all with:
#   pkill -f dws/dw_triggers/

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/triggers"
mkdir -p "$LOG_DIR"

start_one() {
  local name="$1"
  local script="$2"
  shift 2
  if pgrep -f "$script" >/dev/null 2>&1; then
    echo "$name already running — skipping."
    return
  fi
  echo "Starting $name (logs: $LOG_DIR/$name.log)"
  nohup uv run "$script" "$@" >"$LOG_DIR/$name.log" 2>&1 &
  echo "  pid=$!"
}

TRIGGERS_DIR="$ROOT/dws/dw_triggers"

if [ $# -eq 0 ]; then
  cat <<EOF
Usage: $0 <trigger> [<trigger> ...]

Triggers:
  filesystem     watch dw_inbox/ for *.md prompt files
  github-issue   poll for issues with label 'dw-trigger'
  github-pr      poll for PRs with label 'dw-review'
  ci-failure     poll for failed GitHub Actions runs
  all            start all four
EOF
  exit 1
fi

for arg in "$@"; do
  case "$arg" in
    filesystem)
      start_one filesystem "$TRIGGERS_DIR/trigger_filesystem.py"
      ;;
    github-issue)
      start_one github-issue "$TRIGGERS_DIR/trigger_github_issue.py"
      ;;
    github-pr)
      start_one github-pr "$TRIGGERS_DIR/trigger_github_pr.py"
      ;;
    ci-failure)
      start_one ci-failure "$TRIGGERS_DIR/trigger_ci_failure.py"
      ;;
    all)
      start_one filesystem "$TRIGGERS_DIR/trigger_filesystem.py"
      start_one github-issue "$TRIGGERS_DIR/trigger_github_issue.py"
      start_one github-pr "$TRIGGERS_DIR/trigger_github_pr.py"
      start_one ci-failure "$TRIGGERS_DIR/trigger_ci_failure.py"
      ;;
    *)
      echo "Unknown trigger: $arg" >&2
      exit 1
      ;;
  esac
done

echo
echo "Triggers started. Tail logs with:"
echo "  tail -f $LOG_DIR/*.log"
echo "Stop all with:"
echo "  pkill -f dws/dw_triggers/"
