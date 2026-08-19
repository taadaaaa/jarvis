# Jarvis — Plan & Goals

The vision: a user-friendly, everyday voice assistant (inspired by
[this demo](https://www.youtube.com/watch?v=2od7tPirPYE)) that Matt can use
for daily tasks — opening apps, asking about a video he's watching,
analyzing a game on screen, responding to things on his computer.

## Core goals

| Goal | Status | Notes |
|---|---|---|
| Voice loop (hotkey → whisper → LLM → TTS) | ✅ done | streaming, interruptible |
| Desktop app + Command Center UI | ✅ done | py2app, WKWebView HUD |
| Tools (apps, weather, wikipedia, clipboard, volume) | ✅ done | tools.py |
| ElevenLabs voice | ✅ done | falls back to macOS say |
| **Screen share / vision** — "what's on my screen?", analyze games & videos | ✅ done | look_at_screen tool → gemma3:4b (or Claude vision) |
| **Browser actions** — open URLs, know the current tab, web search | ✅ done | open_url / get_browser_tab / search_web tools |
| **Hands-free voice mode** — talk without the hotkey | ✅ done | VAD listener + "jarvis" wake word, toggle in UI/menu |
| **Local file search** — find files by voice | ✅ done | Spotlight (mdfind) + read_text_file tools |
| **Model / brain switching** — swap LLMs at runtime | ✅ done | menu + UI + by voice ("switch to Claude") |

## Later / ideas

- Voice picker UI (ElevenLabs voices, macOS voices)
- Wake-word engine (openWakeWord) instead of transcript matching
- Live listener mode: continuously transcribe system audio (BlackHole)
- Deeper browser control (click/fill via AppleScript or extension)
- Calendar / reminders / notes tools
- Memory: persist conversation highlights across sessions

## Architecture map

- `app.py` — rumps menu bar app, orchestration, state machine
- `window.py` + `ui/index.html` — WKWebView Command Center dashboard
- `audio.py` — recorder (rate-measuring, AirPods-safe)
- `handsfree.py` — always-listening VAD mode with wake word
- `stt.py` — faster-whisper transcription
- `brain.py` — LLM agent loop (Ollama / Claude), runtime-switchable
- `tools.py` — everything Jarvis can DO; add a function + schema to extend
- `vision.py` — screen capture + multimodal model queries
- `tts.py` — ElevenLabs / macOS speech with queue + interrupts
- `config.py` — all knobs
