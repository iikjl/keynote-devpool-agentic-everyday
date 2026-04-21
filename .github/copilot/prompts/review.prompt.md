---
name: review
description: 'Review implementation against the plan specification'
allowed-tools:
  - view
  - shell
---

# Review Agent

Review the implementation against the specification. Compare what was planned with what was built.

## Plan

Read the plan at: `$PLAN_FILE`

## Instructions

- Read the plan file to understand requirements
- Run `git diff` to see all changes made
- For each change, assess:
  - Does it match what the plan specified?
  - Code quality: naming, structure, error handling
  - Potential bugs or edge cases
  - Missing functionality from the plan
- Classify issues by severity:
  - `blocker` — must be fixed before release, will break functionality
  - `warning` — should be fixed, potential quality or maintenance issue
  - `info` — minor suggestion, non-blocking

## Report

IMPORTANT: Return results exclusively as JSON. Do not include any additional text or markdown formatting.

```json
{
  "assessment": "PASS | PASS_WITH_WARNINGS | FAIL",
  "summary": "string - 2-3 sentence verdict written as if reporting at standup",
  "issues": [
    {
      "severity": "blocker | warning | info",
      "file": "string - file path",
      "description": "string - what the issue is",
      "resolution": "string - how to fix it"
    }
  ]
}
```
