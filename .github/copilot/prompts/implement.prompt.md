---
name: implement
description: 'Implement a plan step by step'
allowed-tools:
  - view
  - edit
  - shell
---

# Implementation Agent

Implement the plan step by step. Follow the instructions precisely.

## Plan

Read the plan at: `$PLAN_FILE`

## Instructions

- Read the plan file completely before starting
- Implement each step in the exact order listed
- After each step, verify the change works before proceeding
- Do NOT add features, refactoring, or changes beyond what the plan specifies
- After all steps, run the validation commands from the plan

## Report

- Summarize the work you've just done in a concise bullet point list
- Report the files and total lines changed with `git diff --stat`
