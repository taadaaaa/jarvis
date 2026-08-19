# COMPLETED.md — Jarvis devlog

Newest entries at the top. Each entry: what was built, why I wanted it,
and anything worth remembering about how it works.

<!-- Template for Claude:
## [date] — Feature name
**Why:** (from PLAN.md or Matt's request — the motivation, in plain words)
**What changed:** files touched and a 2-3 sentence explanation
**Commit:** (short hash from `git log --oneline -1`)
**Notes for future me:** gotchas, decisions made, things to revisit
-->

## 2026-08-19 — Project started
**Why:** I wanted a Jarvis-style assistant I could talk to on my Mac —
for quick answers, debate practice, and listening to system audio to help
me respond to videos/calls. Also a fun way to learn by reading every change.
**What changed:** Starter scaffold: menu bar app (app.py), audio capture
(audio.py), Whisper STT (stt.py), Claude/Ollama brain (brain.py), macOS
TTS (tts.py), config with three modes (config.py).
**Notes for future me:** Runs from `python app.py` in the venv. Needs mic
+ Accessibility permissions. System
