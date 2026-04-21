# Agent Layer Primitives - GitHub Copilot SDK

## Value Proposition

This is the **GitHub Copilot SDK variant** of the Agent Layer Primitives. It mirrors the Claude Code SDK version to demonstrate a key thesis:

> The agentic layer pattern is SDK-agnostic. The value is in the templates, specs, and workflows - the model is pluggable.

Instead of chatting with AI tools interactively, we template our engineering patterns and teach agents how to operate our codebases. This variant proves the pattern works across different AI SDKs.

## Side-by-Side: Claude Code SDK vs Copilot SDK

| Component | Copilot SDK (app2) |
|-----------|----------------------|-------------------|
| **Core module** | `agent.py` (JSON-RPC server) |
| **SDK module** | `agent_sdk.py` (copilot-sdk) |
| **Prompt CLI** | `dw_prompt.py` |
| **SDK CLI** | `dw_sdk_prompt.py` |
| **Specs** | `specs/*.md` |
| **Apps** | `apps/` |
| **Output** | `cp_raw_output.jsonl` |

### Architectural Differences

| Aspect | Claude Code | Copilot |
|--------|------------|---------|
| Communication | JSON-RPC server mode |
| Permissions | `onPermissionRequest` handler (required) |
| Models |  Multi-model (Claude, GPT-4o, Gemini) |
| Session |  Full session persistence |
| Output | Streaming events |

## Prerequisites

1. **GitHub Copilot CLI** - Install the Copilot CLI
2. **GitHub Token** - A GitHub PAT with Copilot access
3. **Python 3.10+** with [uv](https://github.com/astral-sh/uv) for single-file script execution

## Quick Start

```bash
# 1. Configure environment
cp .env.sample .env
# Edit .env and add your GITHUB_TOKEN (fine-grained PAT w/ Copilot Requests)

# 2. Run a one-shot prompt (subprocess approach)
./dws/dw_prompt.py "Write a hello world Python script"

# 3. Run via SDK
./dws/dw_sdk_prompt.py "Explain async/await in Python"

# 4. Start an interactive session
./dws/dw_sdk_prompt.py --interactive

# 5. Use a specific model
./dws/dw_prompt.py "Create a REST API" --model gpt-4o
./dws/dw_sdk_prompt.py "Create a REST API" --model claude-sonnet-4
```

For the event-driven setup (GitHub issues/PRs, CI failures, file watcher),
see [Triggers & GitHub integration](#triggers--github-integration) below.

## Codebase Structure

### Agentic Layer

```
dws/                           # AI Developer Workflows
  dw_modules/
    agent.py                    # Core: JSON-RPC to Copilot CLI server
    agent_sdk.py                # SDK: Copilot Python SDK wrapper
  dw_prompt.py                 # CLI: One-shot prompt execution
  dw_sdk_prompt.py             # CLI: SDK-based prompt execution
  README.md                     # DW documentation

specs/                          # Plans for agents to follow
```

### Application Layer

```
apps/                           # Your application code
  main.py                       # Python entry point
  main.ts                       # TypeScript entry point
```

### Triggers & Setup

```
.github/
  ISSUE_TEMPLATE/dw-trigger.yml # Issue form that pre-applies `dw-trigger`
  pull_request_template.md      # Reminds reviewers to add `dw-review`
  copilot/prompts/*.md          # Shared prompt templates
scripts/
  setup-labels.sh               # Create/update the trigger labels via `gh`
  start-triggers.sh             # Background launcher for one or more triggers
dw_inbox/                       # Watched dir for filesystem trigger (*.md)
dws/dw_triggers/                # Event-driven entry points
```

## Triggers & GitHub integration

Four triggers turn external events into DW runs. Each trigger creates a
per-run git branch + worktree under `.dw-worktrees/`, launches the DW via
`dw_runner.py`, and — once the workflow finishes — auto-pushes the branch
and opens a **draft PR** back to `main` linking the source issue / failed
run / inbox file. Many runs can execute in parallel without colliding on
the shared working tree. See
[dws/README.md#branch--worktree-per-run](dws/README.md#branch--worktree-per-run)
for the naming rules, `/branch <type>` directive, and the
`scripts/cleanup-worktrees.sh` helper.

| Trigger | Fires on | Default workflow |
|---|---|---|
| `trigger_filesystem`   | new `*.md` in `dw_inbox/`           | `dw_plan_build` |
| `trigger_github_issue` | issue with label `dw-trigger`       | `dw_plan_build_review_fix` |
| `trigger_github_pr`    | PR with label `dw-review`           | `dw_plan_security_review_patch` |
| `trigger_ci_failure`   | new failed GitHub Actions run       | `dw_prompt` (diagnose-only) |

### 1. One-time GitHub setup

```bash
# Auth the CLI against the target repo (once)
gh auth login
gh repo set-default <owner>/<repo>

# Create/update the `dw-trigger` and `dw-review` labels
./scripts/setup-labels.sh
# or target a specific repo:
REPO=<owner>/<repo> ./scripts/setup-labels.sh
```

`GITHUB_TOKEN` in `.env` must be a **fine-grained** PAT with the
**"Copilot Requests"** permission. Classic `ghp_...` tokens are silently
ignored by the Copilot SDK.

### 2. Start the triggers

```bash
# All four in the background, logging to logs/triggers/*.log
./scripts/start-triggers.sh all

# Or pick a subset
./scripts/start-triggers.sh filesystem github-issue
```

Tail logs with `tail -f logs/triggers/*.log`. Stop everything with
`pkill -f dws/dw_triggers/`.

### 3. Using it

**GitHub issues.** Open an issue using the "DW agent task" template (the
label `dw-trigger` is auto-applied). The issue body is the prompt.

Default workflow is `dw_plan_build_review_fix`. Each issue gets its own
branch + worktree (`feature/dw-<id>-issue-<n>-<slug>`, or `bugfix/` /
`refactor/` depending on keywords) and — when the DW finishes — an
auto-opened draft PR that `closes #<n>`. Override per-issue with
directives anywhere in the body:

```
/workflow dw_plan
/branch refactor
Draft a plan for extracting a response_builder helper from apps/main.py.
```

`/workflow` picks a different DW; `/branch` pins the branch type
(`feature`, `bugfix`, `refactor`). Both are stripped from the prompt.
Unknown names fall back to the defaults with a warning in the trigger log.
The agent posts a `[DW-AGENTS]` comment on the issue when it starts and
again with the PR link when finished.

**Pull requests.** Add the `dw-review` label to any PR. The default
workflow is `dw_plan_security_review_patch` which chains
`plan → security_review → patch` (the patch step loops up to 2 times if
findings remain).

By default the trigger runs in **isolated mode**: for each PR it creates a
detached git worktree at `.dw-worktrees/pr-<number>/`, checks out the PR
head there via `gh pr checkout --detach`, and passes that path to the DW
as `--working-dir`. Patches land in the worktree — your main checkout is
untouched. The `[DW-AGENTS]` comment on the PR tells you which worktree
was used.

Worktrees are kept for review; clean them up with:

```bash
git worktree remove --force .dw-worktrees/pr-<number>
```

Disable isolation (old in-place behaviour) with `--no-isolated`, or switch
to diagnose-only with:

```bash
./dws/dw_triggers/trigger_github_pr.py --workflow dw_prompt
```

**CI failures.** The trigger seeds itself from the current failure list at
startup, so historical failures don't fire. Only new failures that appear
after startup will launch a DW. Default is diagnose-only; opt into auto-fix
with `--workflow dw_plan_build`. If the failed run is associated with a
PR, a `[DW-AGENTS]` comment is posted there.

**Filesystem inbox.** Drop a `.md` file into `dw_inbox/`:

```bash
cat > dw_inbox/add-health-check.md <<'EOF'
Add a /health endpoint to apps/main.py that returns {"status": "ok"}.
Write a test for it in apps/test_main.py.
EOF
```

Processed files are renamed to `*.processed.md`. Empty files are skipped.

### 4. Bot-loop guard

Every comment the triggers post starts with the `[DW-AGENTS]` marker.
Issues and PRs whose body contains that marker are skipped so a DW run
can't fire itself via its own post-back comment.

## Key Copilot SDK Concepts

### Permission Handler (Required)

Every Copilot session requires an `onPermissionRequest` handler. For automated workflows:

```python
async def auto_approve_handler(request):
    """Auto-approve all tool permissions for automated workflows."""
    return {"approved": True}
```

### JSON-RPC Server Mode

Unlike Claude Code's one-shot subprocess, Copilot CLI runs as a persistent server:

```
1. Start: copilot server --port 8080
2. Create session: JSON-RPC -> session/create
3. Send message: JSON-RPC -> session/sendMessage
4. Collect events: JSON-RPC -> session/getEvents
5. Shutdown: terminate process
```

### Multi-Model Support

```bash
# Use GPT-4o
./dws/dw_prompt.py "Explain this" --model gpt-4o

# Use Claude via Copilot
./dws/dw_prompt.py "Explain this" --model claude-sonnet-4

# Use Gemini
./dws/dw_prompt.py "Explain this" --model gemini
```

## 12 Leverage Points of Agentic Coding

### In Agent (Core Four)

1. Context
2. Model
3. Prompt
4. Tools

### Through Agent

5. Standard Output
6. Types
7. Docs
8. Tests
9. Architecture
10. Plans
11. Templates
12. AI Developer Workflows

These leverage points are **SDK-agnostic** - they apply whether you use Claude Code, Copilot, or any other agentic coding tool.
