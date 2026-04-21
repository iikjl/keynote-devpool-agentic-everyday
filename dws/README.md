# AI Developer Workflows (DWs) - Copilot SDK

## Overview

The `dws/` directory contains **AI Developer Workflows** built on the GitHub Copilot SDK. These mirror the Claude Code SDK DWs to demonstrate that the workflow pattern is SDK-agnostic.

## Architecture: JSON-RPC vs Subprocess

The key architectural difference from the Claude Code variant:

### Claude Code Approach (app1)
```
Python script -> subprocess.run([claude, -p, prompt]) -> JSONL stdout -> parse
```
One-shot: start process, get output, done.

### Copilot SDK Approach (app2)
```
Python script -> start server -> JSON-RPC connection -> session/create
                                                     -> session/sendMessage
                                                     -> session/getEvents (streaming)
                                                     -> terminate server
```
Server mode: persistent process, bidirectional communication via JSON-RPC.

## Permission Handler Pattern

The Copilot SDK **requires** an `onPermissionRequest` handler for every session. This is a fundamental design difference from Claude Code's opt-out model (`--dangerously-skip-permissions`).

### Auto-Approve (Automated Workflows)
```python
async def auto_approve_handler(request):
    return {"approved": True}
```

### Logging Handler (Observability)
```python
async def logging_approve_handler(request):
    logger.info(f"Permission: {request.tool_name} - {request.description}")
    return {"approved": True}
```

## Components

### Core Module: `agent.py`

The foundation module providing:
- **CopilotPromptRequest/Response**: Pydantic data models (mirrors AgentPromptRequest/Response)
- **prompt_copilot()**: Execute prompts via Copilot CLI JSON-RPC
- **prompt_copilot_with_retry()**: Execution with automatic retry logic
- **execute_template()**: Slash command template execution
- **JSON-RPC helpers**: `_send_jsonrpc()`, `_collect_streaming_events()`
- **Server lifecycle**: Start, connect, communicate, shutdown

### SDK Module: `agent_sdk.py`

Idiomatic Copilot SDK patterns:
- **simple_query()** - One-shot text queries
- **query_with_tools()** - Operations with tool access
- **create_session()** - Context manager for sessions
- **safe_query()** - Error-handled queries
- **CopilotSessionWrapper** - Clean session interface

### Prompt CLI: `dw_prompt.py`

```bash
./dws/dw_prompt.py "Write a hello world" --model gpt-4o
```

### SDK CLI: `dw_sdk_prompt.py`

```bash
# One-shot
./dws/dw_sdk_prompt.py "Explain this code"

# Interactive
./dws/dw_sdk_prompt.py --interactive

# With tools
./dws/dw_sdk_prompt.py "Create hello.py" --tools file_write,file_read
```

## Composite workflows

Multi-phase DWs that chain single-phase scripts via subprocess. All accept
a prompt + optional `--dw-id`, `--model`, `--working-dir`, and emit
`agents/<dw_id>/workflow_summary.json`.

| Script | Phases | Notes |
|---|---|---|
| `dw_plan_build.py`                 | plan → build | Fastest "build something" flow |
| `dw_plan_build_test.py`            | plan → build → test | Adds a test phase |
| `dw_plan_build_review_fix.py`      | plan → build → review → fix loop (max 2) | Default for issue trigger |
| `dw_plan_security_review_patch.py` | plan → security_review → patch loop (max 2) | Default for PR trigger |
| `dw_sdlc.py`                       | full SDLC pipeline | See the script for details |

The fix/patch loop heuristic: if the review output contains `FAIL`,
`CRITICAL`, `HIGH`, `"blocker"`, or `"severity": "high"`, another fix
iteration fires. Loop exits as soon as a re-review comes back clean or
`MAX_FIX_ATTEMPTS` (2) is reached.

## Branch & worktree per run

Triggers (except PR review, which has its own worktree flow) create a
**per-run git branch + worktree** before firing the DW, so many runs can
execute in parallel without colliding on the shared working tree. After the
DW finishes, `dw_runner.py` pushes the branch and opens a **draft PR** back
to `main` linking the source.

**Branch naming.** `<type>/dw-<dw_id>-<slug>` — type is one of
`feature`, `bugfix`, or `refactor`:

- `/branch <type>` directive in an issue body / filesystem prompt pins the type
- Otherwise inferred from keywords: `fix` / `bug` / `crash` → `bugfix`,
  `refactor` / `rename` / `cleanup` → `refactor`, else `feature`
- CI-failure auto-fix runs always use `bugfix/`

**Worktree layout.** Every run lives under `.dw-worktrees/<branch>/` (the
branch `/` is replaced with `__` in the directory name). `.dw-worktrees/`
is gitignored. Inspect commits with
`git -C .dw-worktrees/<dir> log` and the draft PR link from the trigger log.

**Auto-opened draft PR.** After the DW exits cleanly and produces a commit,
`dw_runner.py` runs `git push -u origin <branch>` then
`gh pr create --draft --base main`. The PR body links `closes #N` / `refs #N`
for issue/PR-sourced runs. If the DW made no edits (diagnose-only, etc.),
the runner exits cleanly without push/PR.

**Cleanup.** Worktrees and DW branches are kept after the run for your
inspection. Batch-clean with:

```bash
./scripts/cleanup-worktrees.sh              # remove all .dw-worktrees/ + local dw-* branches
DRY_RUN=1 ./scripts/cleanup-worktrees.sh    # show what would be removed
```

The PR trigger keeps its original semantics (checks out the PR head detached
for patch review) — it does not auto-push or open a new PR.

## Triggers (`dw_triggers/`)

Event-driven entry points that subprocess-launch `dw_runner.py` (which then
runs the DW) with a prompt extracted from the event. Standalone uv scripts —
no shared services.

**Running them.** The simplest way is the portable launcher at the repo root:

```bash
./scripts/start-triggers.sh all                         # all four
./scripts/start-triggers.sh filesystem github-issue     # subset
tail -f logs/triggers/*.log                             # tail their logs
pkill -f dws/dw_triggers/                               # stop all
```

Each trigger is also a standalone uv script you can run directly (see per-trigger
sections below) when you want custom flags.

**GitHub post-back.** Every GitHub-related trigger (issue, PR, CI failure)
posts a comment to the originating issue/PR when it fires, noting the DW ID,
workflow, and log path. Comments are prefixed with `[DW-AGENTS]` so the
triggers can skip bot-posted content and avoid self-triggering loops. Auth
via `gh auth login` (default) or `GITHUB_PAT` env var. Helper lives in
`dw_modules/github.py`.

**Label setup.** The GitHub triggers rely on two repo labels:
`dw-trigger` (issues) and `dw-review` (PRs). Create them once with
`./scripts/setup-labels.sh` — idempotent; safe to rerun.

### Filesystem: `trigger_filesystem.py`

Watches a directory (default: `dw_inbox/` at project root). Drop an `.md` file
in, and the trigger reads its contents as a prompt and fires `dw_plan_build.py`.
Processed files are renamed to `*.processed.md` so they don't fire twice.
Empty files are skipped.

`dw_inbox/*.md` is gitignored (the README is kept) so dropped prompts don't
accidentally get committed.

```bash
./dws/dw_triggers/trigger_filesystem.py
./dws/dw_triggers/trigger_filesystem.py --watch-dir custom/dir --workflow dw_plan
./dws/dw_triggers/trigger_filesystem.py --workflow dw_plan_build_review_fix
```

### GitHub issue: `trigger_github_issue.py`

Polls `gh issue list --label dw-trigger` every N seconds; each newly-seen
qualifying issue fires a DW with the issue body as the prompt. Requires the
`gh` CLI to be installed and authenticated against the target repo.

**Default workflow:** `dw_plan_build_review_fix`. Each issue lands in a
per-run branch + worktree and ends in an auto-opened draft PR that closes
the issue (see [Branch & worktree per run](#branch--worktree-per-run)).

**Per-issue directives in the issue body:**

- `/workflow <name>` — swap the DW for this issue (trailing `.py` is stripped)
- `/branch <type>` — pin the branch type (`feature`, `bugfix`, or `refactor`)

Both directives are case-insensitive, accept `:` or whitespace separator, and
are stripped from the body before the prompt is sent to the agent.

Example issue body:

```
/workflow dw_plan
/branch refactor
Draft the plan for extracting a response_builder helper from apps/main.py.
```

Unknown workflow names fall back to the trigger's default (from `--workflow`)
with a warning in the trigger log. Unknown branch types fall back to the
keyword-inference heuristic.

```bash
./dws/dw_triggers/trigger_github_issue.py
./dws/dw_triggers/trigger_github_issue.py --label ready-for-dw --interval 30
./dws/dw_triggers/trigger_github_issue.py --workflow dw_plan_build  # change default
```

Issue numbers processed in a session are remembered in-memory — restart the
trigger to re-process them.

### GitHub PR: `trigger_github_pr.py`

Polls `gh pr list --label dw-review` for open PRs. On each newly-seen PR,
fetches the diff via `gh pr diff` and launches a DW with a constructed
review prompt containing PR metadata and the diff.

**Default workflow:** `dw_plan_security_review_patch` (plan →
security_review → patch loop).

**Isolation (default on).** The trigger creates a detached git worktree
per PR at `.dw-worktrees/pr-<number>/`, checks out the PR head there via
`gh pr checkout --detach`, and passes that path to the DW as
`--working-dir`. Patches land in the worktree so the shared working tree
isn't mutated. If worktree setup fails (not a git repo, missing `gh`,
etc.) the trigger logs a warning and falls back to the shared working
dir. Disable with `--no-isolated`.

Worktree cleanup is manual so you can inspect the patches:

```bash
git worktree remove --force .dw-worktrees/pr-<number>
```

Use `--workflow dw_prompt` for diagnose-only behaviour (no patches).

```bash
./dws/dw_triggers/trigger_github_pr.py
./dws/dw_triggers/trigger_github_pr.py --label needs-review --interval 60
./dws/dw_triggers/trigger_github_pr.py --workflow dw_prompt         # diagnose-only
./dws/dw_triggers/trigger_github_pr.py --no-isolated                # in-place
./dws/dw_triggers/trigger_github_pr.py --workflow dw_plan_build_review_fix
```

Diffs are truncated at 20k chars to keep the prompt tractable.

### CI failure: `trigger_ci_failure.py`

Polls `gh run list --status failure` for recent GitHub Actions failures. On
each new failure, fetches the failed-step log via `gh run view --log-failed`
and launches a DW with a diagnose-and-fix prompt containing the log tail.

```bash
./dws/dw_triggers/trigger_ci_failure.py
./dws/dw_triggers/trigger_ci_failure.py --workflow-name tests.yml --interval 120
./dws/dw_triggers/trigger_ci_failure.py --workflow dw_plan_build   # opt into auto-fix
```

Seeds its processed-set from the current failure list at startup so historical
failures don't fire on first launch. Default DW is `dw_prompt` (diagnose only,
no branch) to avoid auto-editing on flaky tests; pass `--workflow dw_plan_build`
to close the loop — auto-fix runs land in a `bugfix/dw-<id>-ci-<run>` branch
+ worktree and open a draft PR when complete.

Post-back: if the failed run is associated with a PR, a comment is posted
there. Runs on main (no PR) still fire the DW but skip post-back.

### Schedule: `trigger_schedule.py`

Time-driven counterpart to the polling triggers — uses `schedule` to fire a
DW at a fixed interval or daily wall-clock time. Good for nightly/periodic
batch work.

```bash
# Every 6 hours
./dws/dw_triggers/trigger_schedule.py --every 6h \
    --prompt "Audit apps/main.py for dead code"

# Daily at 02:00 local
./dws/dw_triggers/trigger_schedule.py --at 02:00 \
    --workflow dw_prompt \
    --prompt "Review apps/main.py for OWASP top 10 issues"

# One-shot (useful under system cron)
./dws/dw_triggers/trigger_schedule.py --once --prompt "..."
```

Interval syntax: `30s`, `15m`, `6h`, `1d`. Exactly one of `--every`, `--at`,
or `--once` is required.

## Output Structure

Same convention as Claude Code, with `cp_` prefix:

```
agents/
  {dw_id}/
    {agent_name}/
      cp_raw_output.jsonl        # Raw streaming events
      cp_raw_output.json         # Parsed JSON array
      cp_final_object.json       # Final result object
      custom_summary_output.json # High-level summary (SDK-agnostic name)
```

## SDK vs Subprocess Comparison

| Feature | Subprocess (agent.py) | SDK (agent_sdk.py) |
|---------|----------------------|-------------------|
| Type Safety | Pydantic models | Dataclass types |
| Error Handling | RetryCode enum | Exception-based |
| Async Support | Subprocess + polling | Native async/await |
| Interactive Sessions | Via JSON-RPC | CopilotSessionWrapper |
| Permission Model | autoApprove param | Handler callbacks |
| Multi-model | --model flag | Config object |
