---
name: patch
description: 'Fix issues found by review or security review'
allowed-tools:
  - view
  - edit
  - shell
---

# Patch Agent

Fix the issues described below. Apply minimal, targeted changes — do not refactor or add unrelated improvements.

## Review Output

The following issues were found and need to be fixed:

```
$REVIEW_OUTPUT
```

## Plan

The original plan is at: `$PLAN_FILE`

## Instructions

- Read the review output carefully to understand each issue
- For each issue that has severity `blocker`, `critical`, or `high`:
  - Locate the file and code mentioned
  - Apply the resolution described in the issue
  - Verify the fix works
- For `medium` severity issues: fix if the change is small and safe
- For `low`, `info`, or `warning` severity: skip unless trivial
- Do NOT introduce new features or refactor unrelated code
- After all fixes, run the validation commands from the plan

## Report

- List each issue you fixed with a one-line summary
- List any issues you intentionally skipped and why
- Report `git diff --stat`
