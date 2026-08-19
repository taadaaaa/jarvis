# CLAUDE.md — Jarvis project

## What this is
A macOS menu bar voice assistant: hotkey toggle → record → Whisper STT →
Claude API or Ollama → macOS TTS. Owner is learning as they go — this
project is for fun and education, not production.

## How to work in this repo
- **Always start by reading PLAN.md.** Implement the topmost incomplete
  task unless told otherwise.
- **After finishing any task, add an entry to the top of COMPLETED.md**
  using the template in that file: what was built, why (pull the
  motivation from PLAN.md or ask me), and notes for future me. This
  devlog is the project's memory — never skip it.
- **Teach while you build.** After implementing, give a short plain-English
  explanation of what you changed and why — the owner reads every diff to
  learn. Prefer simple, readable code over clever code.
- One task per session unless asked. Small commits, descriptive messages.
- Ask before adding new dependencies.

## Project conventions
- Python 3, standard library where possible.
- Config lives in config.py — no magic numbers scattered in modules.
- Never commit .env, venv/, or __pycache__ (already gitignored).
- TTS replies are spoken aloud: any system prompt changes must keep
  responses short and formatting-free.

## Testing reality
Audio (mic, BlackHole, TTS) can only be verified by the owner running
`python app.py` on their Mac. After audio-related changes, tell the owner
exactly what to run and what they should hear/see.
