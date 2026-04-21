#!/usr/bin/env bash
# Create the GitHub labels used by the DW triggers.
# Requires `gh` CLI authenticated against the target repo.
#
# Usage:
#   ./scripts/setup-labels.sh
#   REPO=owner/repo ./scripts/setup-labels.sh

set -euo pipefail

REPO_ARG=()
if [ "${REPO:-}" != "" ]; then
  REPO_ARG=(--repo "$REPO")
fi

create_label() {
  local name="$1"
  local description="$2"
  local color="$3"
  if gh label list ${REPO_ARG[@]+"${REPO_ARG[@]}"} --limit 200 --json name -q '.[].name' | grep -qx "$name"; then
    echo "Label '$name' exists — updating."
    gh label edit "$name" ${REPO_ARG[@]+"${REPO_ARG[@]}"} --description "$description" --color "$color"
  else
    echo "Creating label '$name'."
    gh label create "$name" ${REPO_ARG[@]+"${REPO_ARG[@]}"} --description "$description" --color "$color"
  fi
}

create_label "dw-trigger" "Issue picked up by the DW agent (trigger_github_issue)" "5319E7"
create_label "dw-review"  "PR picked up by the DW agent for review (trigger_github_pr)" "0E8A16"

echo "Done."
