# Devpool Keynote — "AI-Assisted Development in Action"

15-minute keynote with slides + embedded speaker notes.

## Files
- `keynote.md` — Marp-compatible markdown. Slides + speaker notes (in HTML comments).
- `demo-commands.md` — Copy-paste commands for the live demo, in order.

## Render slides

Install Marp CLI once:
```bash
npm install -g @marp-team/marp-cli
```

Export to PDF:
```bash
marp keynote.md --pdf --allow-local-files
```

Export to PPTX:
```bash
marp keynote.md --pptx --allow-local-files
```

Present directly in browser (with speaker notes in presenter view):
```bash
marp keynote.md --preview
# or
marp keynote.md --server
```

VS Code alternative: install the **Marp for VS Code** extension, open
`keynote.md`, click the preview button.

## Timing (15 min total)

| Section | Slide | End at |
|---------|-------|--------|
| Title | 1 | 0:15 |
| Hook | 2 | 1:00 |
| Who I am | 3 | 1:30 |
| 4 levels | 4 | 4:00 |
| Agent definition | 5 | 4:30 |
| My journey | 6 | 5:00 |
| Three skills | 7 | 7:00 |
| Proof | 8 | 9:00 |
| Demo intro | 9 | 9:15 |
| Demo A | 10 | 10:15 |
| Demo B | 11 | 11:45 |
| Demo C | 12 | 13:30 |
| Takeaway | 13 | 14:30 |
| Your move | 14 | 15:00 |
| Thank you / Q&A | 15 | — |

## Pre-flight checklist

- [ ] Rehearse once end-to-end with stopwatch
- [ ] Stage `copilot-demo/` — `cd` into it, confirm `.env` has token
- [ ] Pre-run demos A and B once to warm caches
- [ ] Have a pre-recorded `cp_raw_output.jsonl` ready as fallback if demo C fails
- [ ] Terminal font size bumped for projector
- [ ] Slides rendered + loaded on presenting machine
- [ ] Water nearby
