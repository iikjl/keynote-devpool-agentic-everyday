# dw_inbox

Drop any `.md` file into this directory and `dws/dw_triggers/trigger_filesystem.py`
(when running) will read its contents as a prompt and launch a DW in the
background.

Processed files are renamed to `*.processed.md` so the trigger won't fire on
them twice. Empty files are skipped.

## Example

```bash
# Start the watcher (in another terminal)
./scripts/start-triggers.sh filesystem

# Drop a prompt
cat > dw_inbox/add-health-check.md <<'EOF'
Add a /health endpoint to apps/main.py that returns {"status": "ok"}.
Write a test for it in apps/test_main.py.
EOF
```

You can also choose a different DW or model:

```bash
./dws/dw_triggers/trigger_filesystem.py --workflow dw_plan --model gpt-4o
```
