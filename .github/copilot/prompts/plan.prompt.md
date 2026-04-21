---
name: plan
description: 'Create a structured implementation plan for a task'
allowed-tools:
  - view
  - shell
---

# Planning Agent

Create a structured implementation plan for the task described below. Follow the instructions precisely.

## Task

$PROMPT

## Instructions

- Research the codebase to understand the current architecture
- Read the `README.md` file first for project overview
- Identify which files need to be created or modified
- Break the work into ordered, actionable steps
- Write the plan to `specs/plan-$DW_ID-$SLUG.md` using the Plan Format below
- Do NOT implement anything — only plan

## Relevant Files

Focus on:
- `apps/` — Application code (the target for changes)
- `README.md` — Project overview
- Any files directly related to the task

## Plan Format

Write the plan file with this exact structure:

```md
# Plan: <descriptive title>

## Metadata
dw_id: `$DW_ID`
prompt: `$PROMPT`

## Summary
<2-3 sentences describing what will be done and why>

## Relevant Files
<list files that need to be read or modified, with brief justification>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. <First step title>
- <specific actions>
- <files to modify>

### 2. <Second step title>
- <specific actions>

### N. Run Validation
- <commands to verify the work>

## Validation Commands
<list commands to validate the work is complete with zero regressions>
```

## Report

IMPORTANT: Return exclusively the relative path to the plan file you created and nothing else.
For example: `specs/plan-a1b2c3d4-add-health-check.md`
