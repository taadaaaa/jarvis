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

## 2026-08-19 — Claude Code as a brain (use my Claude account)
**Why:** I wanted Jarvis connected to my Claude account instead of paying
separately for API access.
**What changed:** brain.py grew a third provider, "claude-code", that runs
the Claude Code CLI headless (`claude -p --output-format stream-json`) with
my existing login — no API key. It streams like the other brains, keeps
conversation continuity via `--resume <session-id>`, and brings Claude
Code's own read-only tools (file reading, web search). app.py added it to
the Brain menu and a "Claude Code · Your account" card in the UI.
**Notes for future me:** Jarvis's own tools (screen vision, volume, etc.)
don't run on this brain — Claude Code has its own toolset instead. Slower
to first word (~few seconds of CLI startup) but much smarter than llama3.1.
Deliberately restricted to read-only tools since it's voice-triggered.
The CLI lives in an nvm path the app bundle can't see — find_claude_cli()
probes known locations. Clear Conversation resets the session id.

## 2026-08-19 — The big framework: vision, browser, files, hands-free, brain switching
**Why:** The four goals from the video demo (see PLAN.md): use Jarvis for
everyday tasks — ask about what's on screen, hands-free talking, finding
local files, and swapping which model powers it.
**What changed:**
- vision.py (new): screenshots the screen (downscaled) and asks a local
  multimodal model (gemma3:4b, pulled via Ollama) or Claude vision if an
  API key is ever set. Exposed as the `look_at_screen` tool.
- tools.py: seven new tools — look_at_screen, open_url, get_browser_tab
  (Chrome/Safari via AppleScript), search_web (DuckDuckGo), search_files
  (Spotlight/mdfind), read_text_file, switch_brain.
- handsfree.py (new): always-on listening with an energy-based voice
  detector; utterances gated by the wake word ("jarvis" in the sentence);
  pauses itself while Jarvis is thinking/speaking so he never hears himself.
- brain.py: runtime `switch(target)` between Ollama models and Claude;
  models that don't support tools (gemma3) fall back to plain chat.
- app.py/ui: Hands-Free toggle (voice panel + quick commands + menu),
  clickable brain cards (◈ marks the active one), Brain menu.
**Notes for future me:** First screen question from the app will trigger a
macOS Screen Recording permission prompt — approve it for Jarvis. Wake word
lives in config.WAKE_WORD (None = respond to everything; don't, with videos
playing). Two subagents built vision and hands-free in parallel.

## 2026-08-19 — ElevenLabs voice
**Why:** The macOS voice is robotic; I picked an ElevenLabs voice.
**What changed:** tts.py rebuilt around a shared queue base class with two
backends: SaySpeaker (macOS) and ElevenLabsSpeaker (API → mp3 → afplay).
Config selects via TTS_PROVIDER. Any API failure (quota, offline) falls
back to the macOS voice per-sentence, so Jarvis never goes mute.
**Notes for future me:** The community voice I originally picked
(bfGb7JTLUnZebZRiFYyq) needs a paid ElevenLabs plan for API use — we're on
premade "Adam" (pNInz6obpgDQGcFmaJgB), free tier (~10 min audio/month).
Swap the ID in config.py if I upgrade. Key in .env (TTS-only scoped).

## 2026-08-19 — Jarvis went deaf: two mic bugs
**Why:** After the window rebuild + switching to AirPods, Jarvis heard
nothing.
**What changed:** (1) Rebuilding the app changes its code signature, which
silently invalidates the Microphone permission — fixed with
`tccutil reset Microphone local.matt.jarvis` + re-allow; documented in
build_app.sh and README. (2) audio.py: AirPods mics record at 24kHz but the
code assumed 16kHz, so Whisper got slowed-down sludge. The recorder now
opens at the device's native rate, measures the *actual* rate against wall
clock (drivers lie), and resamples to 16kHz.
**Notes for future me:** If Jarvis ever stops hearing after `./build_app.sh`,
it's the TCC signature thing. The rate measurement lives in Recorder.stop().

## 2026-08-19 — Command Center UI (the sci-fi dashboard)
**Why:** I wanted the app to look like a JARVIS HUD (reference screenshot),
not a plain window.
**What changed:** window.py now hosts a WKWebView rendering ui/index.html —
a full dashboard: animated particle globe, live clock, real CPU/RAM/disk
rings (psutil), Core Systems status cards, a Live Intelligence Feed that is
the actual conversation transcript (streaming in), state-reactive mic +
talk button, quick commands. Python↔JS via evaluateJavaScript and a script
message handler. Replaced the earlier native AppKit chat window built the
same day.
**Notes for future me:** Restyling = editing ui/index.html, no rebuild.
Found along the way: the bundle's cwd isn't the project dir, so
load_dotenv needed an explicit path (ElevenLabs key was silently unseen).

## 2026-08-19 — Desktop app (Jarvis.app)
**Why:** I wanted a real double-clickable app, not a terminal script.
**What changed:** build_app.sh builds /Applications/Jarvis.app with py2app
in *alias mode* — the bundle symlinks back to this folder, so code edits
apply on next launch without rebuilding. Emoji-rendered .icns icon,
ad-hoc signed.
**Notes for future me:** A hand-rolled script-launcher bundle DOESN'T work:
launched via Finder, macOS parks the menu bar icon off-screen (found by
reading its AX position: parked items sit at (-1,944), visible ones at
y≈4). py2app's compiled launcher fixes it. Also: LaunchServices runs
script bundles under Rosetta — that's why arch matters. Startup voice
announcement added so a launch is always audible.

## 2026-08-19 — Tools: Jarvis can DO things + knows the date
**Why:** Jarvis confidently made up the date (LLMs have no clock), and I
wanted it to act, not just talk.
**What changed:** brain.py injects the real date/time into the system
prompt every request. New tools.py + an agent loop in respond_stream():
the model can call tools (open_app, read_clipboard, set_volume,
get_weather via open-meteo, search_wikipedia) and speak the result. Works
on both providers, streaming preserved.
**Notes for future me:** llama3.1 8B overcalls tools (once opened Notes
unprompted) — the system prompt has a restraint line, tuned so small talk
stays natural. Wikipedia needs a User-Agent header.

## 2026-08-19 — Ollama brain (free/local) + app running end-to-end
**Why:** I chose the free path over an API key (switchable later — and it
was, same day).
**What changed:** Installed Ollama as a brew login service, pulled
llama3.1, PROVIDER="ollama" in config. Set up the venv, pre-downloaded
Whisper base.en, verified STT with synthesized speech.
**Notes for future me:** Warm llama3.1 replies start speaking in ~0.8s;
first request after idle pays a ~10s model-load cost.

## 2026-08-19 — Streaming replies
**Why:** Top payoff-per-effort upgrade: cut the wait before Jarvis speaks.
**What changed:** brain.respond_stream() yields sentences as they generate;
tts.Speaker became a feed()/wait()/stop() queue; app.py wires them so the
first sentence is spoken while the rest is still generating. Hotkey
interrupts cancel both generation and speech (also fixed: interrupt while
thinking used to do nothing).
**Notes for future me:** Sentence splitting is a regex on .!? boundaries;
history always gets an assistant entry (API requires alternating roles),
"[interrupted]" if nothing was spoken.

## 2026-08-19 — Project started
**Why:** I wanted a Jarvis-style assistant I could talk to on my Mac —
for quick answers, debate practice, and listening to system audio to help
me respond to videos/calls. Also a fun way to learn by reading every change.
**What changed:** Starter scaffold: menu bar app (app.py), audio capture
(audio.py), Whisper STT (stt.py), Claude/Ollama brain (brain.py), macOS
TTS (tts.py), config with three modes (config.py).
**Notes for future me:** Runs from `python app.py` in the venv. Needs mic
+ Accessibility permissions. System
