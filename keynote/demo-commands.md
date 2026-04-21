# Demo commands — paste in order

All commands run from `copilot-demo/`:

```bash
cd copilot-demo
```

## Demo A — single prompt (9:15-10:15)

```bash
./dws/dw_prompt.py "Add input validation to apps/main.py"
```

While it runs, narrate: "One-shot subprocess. I prompt, it codes. This is
where most of you are today."

After: show the diff briefly.
```bash
git diff apps/main.py
```

## Demo B — SDK orchestration (10:15-11:45)

```bash
./dws/dw_sdk_prompt.py "Review apps/main.py for OWASP top 10 issues" --model claude-sonnet-4
```

Narrate: "Same idea, but now the agent is a Python function. Multi-model.
Swappable. Composable. This is the level 4 unlock."

## Demo C — event-triggered (11:45-13:30)

Start the trigger polling:
```bash
./dws/dw_triggers/trigger_github_issue.py --label dw-trigger --interval 15
```

In a second terminal or browser, create a pre-prepared issue with the
`dw-trigger` label (or have one ready to label with one click).

Narrate while polling/running: "Agent wakes up on the event. I'm not in the
loop."

Show the output after:
```bash
ls agents/
cat agents/*/cp_final_object.json | head -30
```

## Fallback if Demo C live run fails

Have a pre-recorded JSONL ready at `agents/demo-fallback/cp_raw_output.jsonl`.
Walk through it instead:

```bash
cat agents/demo-fallback/cp_final_object.json
```

Say: "In the interest of time, here's a run I did this morning —"
